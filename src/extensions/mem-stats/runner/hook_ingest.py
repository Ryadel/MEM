"""Stop / SessionEnd hook for Claude Code and Codex: ingest the session's log into the mem-stats ledger, in the
background, at no cost in model tokens.

The hook reads the event from stdin (session_id, transcript_path, hook_event_name, cwd), queues one job for that
transcript and, unless an ingestion already holds the ledger's lock, starts a detached worker, then returns at once:
exit 0, nothing on stdout or stderr, so nothing ever reaches the model's context and the user's turn never fails.

The worker (the same script with --worker) takes the lock, waits --settle seconds so the client finishes writing the
turn, runs the adapter (claude_code.py for Claude Code, with the session's subagent transcripts; codex.py for Codex)
on each queued transcript, and repeats while new jobs arrived meanwhile, at most a few rounds. Jobs are one file per
transcript, so the queue never grows beyond the sessions in use; a job left behind is picked up by the next run. A
job is claimed while its adapter runs and deleted only once the run succeeded: a failed one goes back to the queue
for the next worker run, at most 3 runs, then is dropped with a line in --log. A lock older than --stale-minutes is
taken over; setup.py's backfill takes the same lock.

--log receives one JSON line per run (time, client, event, session id, exit code, duration, the adapter's counts) and
never any content. Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROUNDS = 5  # worker rounds over the job queue before leaving the rest to the next run
ATTEMPTS = 3  # worker runs a failing job gets before it is dropped (and logged)
LOG_LIMIT = 1 << 20  # rotate the run log beyond 1 MB
COUNTS = ("inserted", "files", "requests_pending", "requests_emitted", "compressed_skipped", "unreadable_lines")
SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tmp"}  # .tmp: MEM's agent_tmp_dir default; test KBs live there


def stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def log(path, entry):
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.stat().st_size > LOG_LIMIT:
            path.replace(path.with_name(path.name + ".1"))
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError:
        pass


class Paths:
    def __init__(self, db):
        self.db = Path(db)
        self.lock = self.db.with_name(self.db.name + ".ingest.lock")
        self.queue = self.db.with_name(self.db.name + ".ingest-queue")


def locked(paths, stale):
    """True while a fresh lock exists; a stale one does not count."""
    try:
        return time.time() - paths.lock.stat().st_mtime < stale
    except OSError:
        return False


def acquire(paths, stale):
    for _ in range(2):
        try:
            handle = os.open(paths.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if locked(paths, stale):
                return False
            try:  # stale: a worker died holding it
                paths.lock.unlink()
            except OSError:
                return False
            continue
        os.write(handle, json.dumps({"pid": os.getpid(), "at": stamp()}).encode("utf-8"))
        os.close(handle)
        return True
    return False


def release(paths):
    try:
        paths.lock.unlink()
    except OSError:
        pass


def detect(event, forced):
    if forced:
        return forced
    path = (event.get("transcript_path") or "").replace("\\", "/")
    if "rollout-" in path or "/.codex/" in path or "turn_id" in event:
        return "codex"
    return "claude"


def queue(paths, job):
    """One file per transcript (or session): a repeated Stop replaces the job instead of adding one."""
    key = hashlib.sha1((job["client"] + "|" + (job.get("transcript") or job.get("session") or "")).encode("utf-8"))
    paths.queue.mkdir(parents=True, exist_ok=True)
    target = paths.queue / (key.hexdigest()[:20] + ".json")
    temporary = target.with_suffix(".tmp-" + str(os.getpid()))
    temporary.write_text(json.dumps(job), encoding="utf-8")
    temporary.replace(target)


def pending(paths, skip=()):
    try:
        return sorted(f for f in paths.queue.glob("*.json") if f.name not in skip)
    except OSError:
        return []


def take(paths, skip=()):
    """Claim the queued jobs, [(claim, job)]: each file becomes <name>.running while its adapter runs, so a Stop
    arriving meanwhile queues afresh beside it and nothing is lost if the run fails. Claims left by a worker that died
    (only the lock holder calls this) go back to the queue first, unless a newer job replaced them."""
    try:
        for orphan in paths.queue.glob("*.json.running"):
            try:
                if orphan.with_suffix("").exists():
                    orphan.unlink()
                else:
                    orphan.replace(orphan.with_suffix(""))
            except OSError:
                pass
    except OSError:
        pass
    jobs = []
    for file in pending(paths, skip):
        claim = file.with_name(file.name + ".running")
        try:
            file.replace(claim)
            jobs.append((claim, json.loads(claim.read_text(encoding="utf-8"))))
        except OSError:
            continue
        except ValueError:  # unreadable: never runnable
            claim.unlink(missing_ok=True)
    return jobs


def settle(claim, job, entry):
    """Delete a claim once its run succeeded; put a failed one back for the next worker run, at most ATTEMPTS runs.
    True when it went back."""
    target = claim.with_suffix("")
    try:
        if entry.get("exit", 0) == 0 and "error" not in entry:
            claim.unlink()
            return False
        job["attempts"] = int(job.get("attempts") or 0) + 1
        if job["attempts"] >= ATTEMPTS or target.exists():  # a newer job for the same transcript covers it
            entry.setdefault("decision", "dropped after %d attempts" % job["attempts"] if job["attempts"] >= ATTEMPTS
                             else "superseded")
            claim.unlink()
            return False
        claim.write_text(json.dumps(job), encoding="utf-8")
        claim.replace(target)
        entry["decision"] = "retry later (attempt %d)" % job["attempts"]
        return True
    except OSError:
        return False


def kb_roots(folder, depth=4):
    """KB roots (folders holding MEM.md and MEM.config.md) under the session's working folder."""
    if not folder:
        return []
    found, frontier = [], [Path(folder)]
    for _ in range(depth + 1):
        following = []
        for current in frontier:
            if (current / "MEM.md").is_file() and (current / "MEM.config.md").is_file():
                found.append(current)
            try:
                following += [p for p in current.iterdir() if p.is_dir() and p.name not in SKIP]
            except OSError:
                pass
        frontier = following
    return found


def codex_rollout(session, home):
    if not session:
        return None
    base = Path(home or os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"
    found = sorted(base.glob("*/*/*/rollout-*" + session + ".jsonl"))
    return found[-1] if found else None


def adapter_command(args, job):
    folder = Path(args.adapter_dir)
    python = str(args.python or sys.executable)
    if job["client"] == "codex":
        rollout = job.get("transcript") or codex_rollout(job.get("session"), args.codex_home)
        if not rollout:
            return None
        return [python, "-I", "-B", str(folder / "codex.py"), "--rollout", str(rollout), "--db", str(args.db)]
    transcript = job.get("transcript")
    if not transcript:
        return None
    transcript = Path(transcript)
    command = [python, "-I", "-B", str(folder / "claude_code.py"), "--transcript", str(transcript)]
    for sub in sorted((transcript.parent / transcript.stem / "subagents").glob("*.jsonl")):
        command += ["--transcript", str(sub)]
    roots = list(args.kb_root) + (kb_roots(job.get("cwd")) if args.find_kb and not args.kb_root else [])
    for root in roots:
        command += ["--kb-root", str(root)]
    command += ["--quiet", str(max(args.settle - 1, 0)), "--db", str(args.db)]
    return command


def run(args, job):
    entry = {"at": stamp(), "client": job["client"], "event": job.get("event"), "session": job.get("session")}
    command = adapter_command(args, job)
    if command is None:
        entry["decision"] = "no-transcript"
        return entry
    started = time.monotonic()
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                timeout=max(args.stale_minutes * 60 - 60, 60), **hidden())
        entry["exit"] = result.returncode
        last = (result.stderr.decode("utf-8", "replace").strip().splitlines() or [""])[-1]
        try:  # the adapter's coverage summary: counts only
            summary = json.loads(last)
            entry.update({k: summary[k] for k in COUNTS if isinstance(summary.get(k), int)})
        except ValueError:
            if result.returncode:
                entry["error"] = last[:300]
    except subprocess.TimeoutExpired:
        entry.update(exit=None, error="timeout")
    entry["seconds"] = round(time.monotonic() - started, 3)
    return entry


def hidden():
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def worker(args):
    paths = Paths(args.db)
    stale = args.stale_minutes * 60
    failed = set()  # jobs that failed in this run wait for the next one
    for _ in range(2):  # a job queued while the lock was being released gets one more pass
        if not acquire(paths, stale):
            return
        try:
            for _ in range(ROUNDS):
                if not pending(paths, failed):
                    break
                time.sleep(args.settle)
                jobs = take(paths, failed)
                if not jobs:
                    break
                for claim, job in jobs:
                    os.utime(paths.lock)
                    entry = run(args, job)
                    if settle(claim, job, entry):
                        failed.add(claim.with_suffix("").name)
                    log(args.log, entry)
        finally:
            release(paths)
        if not pending(paths, failed):
            return


def spawn(args, errors):
    """Start the worker apart from the client: a hidden console of its own, no inherited handles, its own group."""
    command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--worker"] + args.passed
    options = {"stdin": subprocess.DEVNULL, "stdout": errors, "stderr": errors, "close_fds": True}
    if os.name == "nt":
        # Not DETACHED_PROCESS: it overrides CREATE_NO_WINDOW and leaves the worker with no console at all, so when
        # sys.executable is a launcher (a venv's python.exe, py.exe, the Store alias) the real interpreter it starts
        # opens a new, visible console window. A hidden console is inherited by every child instead.
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        try:  # leave the client's job object too, when it allows it, so closing the client does not kill the worker
            subprocess.Popen(command, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **options)
        except OSError:
            subprocess.Popen(command, creationflags=flags, **options)
    else:
        subprocess.Popen(command, start_new_session=True, **options)


def hook(args):
    entry = {"at": stamp()}
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
        client = detect(event, args.client)
        job = {"client": client, "event": event.get("hook_event_name"), "session": event.get("session_id"),
               "transcript": event.get("transcript_path"), "cwd": event.get("cwd")}
        entry.update(client=client, event=job["event"], session=job["session"])
        paths = Paths(args.db)
        queue(paths, job)
        if locked(paths, args.stale_minutes * 60):
            entry["decision"] = "queued"  # the running worker, or the next one, takes it
            log(args.log, entry)
            return
        errors = args.log.with_name(args.log.stem + ".err") if args.log else Path(os.devnull)
        if args.log:
            errors.parent.mkdir(parents=True, exist_ok=True)
        with open(errors, "ab") as stream:
            spawn(args, stream)
    except Exception as error:  # never fail the user's turn
        entry["decision"] = "error: " + type(error).__name__
        log(args.log, entry)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, required=True, help="mem-stats ledger (created by stats.py init)")
    parser.add_argument("--client", choices=("claude", "codex"), help="default: recognised from the event")
    parser.add_argument("--kb-root", type=Path, action="append", default=[], help="KB root for MEM attribution")
    parser.add_argument("--find-kb", action="store_true", help="without --kb-root, look for KB roots under the cwd")
    parser.add_argument("--python", type=Path, help="interpreter for the adapters (default: this one)")
    parser.add_argument("--adapter-dir", type=Path, default=Path(__file__).resolve().parent,
                        help="folder holding claude_code.py and codex.py (default: this script's)")
    parser.add_argument("--codex-home", type=Path, help="where to find a rollout the event does not name")
    parser.add_argument("--log", type=Path, help="JSONL of runs, counts only")
    parser.add_argument("--settle", type=float, default=3, help="seconds to let the client finish writing")
    parser.add_argument("--stale-minutes", type=float, default=30, help="age after which a lock is taken over")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    try:
        args = parser.parse_args()
    except SystemExit:
        return  # a broken command line must not fail the turn either
    args.passed = [a for a in sys.argv[1:] if a != "--worker"]
    if args.worker:
        try:
            worker(args)
        except Exception as error:
            log(args.log, {"at": stamp(), "decision": "worker error: " + type(error).__name__})
    else:
        hook(args)


if __name__ == "__main__":
    if "--worker" not in sys.argv:
        sys.stderr = open(os.devnull, "w")  # argparse and anything else stay off the client's output
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
