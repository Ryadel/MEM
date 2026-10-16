"""mem-stats automatic ingestion for Claude Code and Codex: turn the setup answers into hook entries, apply them,
undo them.

  plan    --answers FILE   show every file and hook the answers would change; writes nothing
  apply   --answers FILE   copy the runners, create the ledger (stats.py init), back up each settings file, write
                           exactly what `plan` shows, then backfill the history once (progress on stderr, counts at
                           the end)
  reset [--delete-ledger]  remove mem-stats's hooks; the ledger is kept unless --delete-ledger
  status                   hooks present per client; ledger path and size, last ingestion, lock and queue

The hook (runner/hook_ingest.py) runs at the end of every agent turn (Stop; for Claude Code also SessionEnd, which
covers /clear and exit), starts the adapter detached in the background and returns at once, printing nothing: it
costs no model tokens. There is one ledger per user, for every project (the ledger tells projects apart): hooks go in
~/.claude/settings.json and ~/.codex/hooks.json, the runners are copied to ~/.mem/mem-stats/<version>/runner, and the
ledger, its run log, lock and queue live in ~/.mem/mem-stats/state. Codex runs a new or changed hook only after the
user trusts it (/hooks). Hook entries are recognised by the runner name, so `apply` replaces them instead of adding
duplicates, a client no longer chosen loses them, and other tools' hooks (mem-optimize's included) are never touched.
The setup log and the settings backups are kept in ~/.mem/mem-stats (setup-log.json, backups/<stamp>/).

Answers (JSON; every key optional):
  {"clients": ["claude", "codex"],      default ["claude"]
   "backfill": true,                    default true: ingest every existing session of the chosen clients on this
                                        host once, at apply
   "ledger": "path/to/stats.sqlite",    advanced; default ~/.mem/mem-stats/state/stats.sqlite
   "python": "path/to/python",          interpreter the hook runs with; default --python
   "adapter_python": "path/to/python"}  interpreter for the adapters, e.g. Python 3.14 to read Codex .jsonl.zst
                                        rollouts; default the hook's
An earlier `scope`/`scopes` answer is ignored.

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

EXTENSION = "mem-stats"
STALE = 30 * 60  # hook_ingest.py's default --stale-minutes: a lock untouched for longer is a dead worker's
RUNNERS = ("hook_ingest.py", "claude_code.py", "codex.py", "stats.py")
MARK = re.compile(r"mem-stats.*/hook_ingest\.py")
CLIENTS = ("claude", "codex")
CLIENT_NAMES = {"claude": "Claude Code", "codex": "Codex"}
EVENTS = {"claude": ("Stop", "SessionEnd"), "codex": ("Stop",)}  # Codex has no SessionEnd
ADAPTERS = {"claude": "claude_code.py", "codex": "codex.py"}


def posix(path):
    return Path(path).expanduser().resolve().as_posix()


def quoted(path):
    # Claude Code runs hooks through a shell (Git Bash on Windows, which strips backslashes): forward slashes, quoted.
    # Codex on Windows wraps the line as cmd.exe /C "<command>", which accepts the same form.
    return '"' + posix(path) + '"'


class Layout:
    def __init__(self, args):
        self.home, self.extension = Path(args.home).expanduser(), Path(args.extension_dir).resolve()
        self.python = args.python
        self.clients = (args.client,) if args.client else CLIENTS
        self.version = re.search(r"\*\*version\*\*:\s*(\S+)",
                                 (self.extension / "index.md").read_text(encoding="utf-8")).group(1)
        self.base = self.home / ".mem" / EXTENSION
        self.runner, self.state = self.base / self.version / "runner", self.base / "state"
        self.setup_log, self.backups = self.base / "setup-log.json", self.base / "backups"

    def settings(self, client):
        return self.home / ".codex" / "hooks.json" if client == "codex" else self.home / ".claude" / "settings.json"


class Choice:
    """The answers, with their defaults resolved."""

    def __init__(self, answers, layout):
        self.clients = [c for c in (answers.get("clients") or ["claude"]) if c in CLIENTS]
        self.ledger = Path(answers["ledger"]).expanduser() if answers.get("ledger") else layout.state / "stats.sqlite"
        self.log = layout.state / "ingest.jsonl"
        self.backfill = bool(answers.get("backfill", True))
        self.python = Path(answers.get("python") or layout.python)
        self.adapter_python = Path(answers.get("adapter_python") or self.python)


def hook_command(layout, choice, client):
    # --find-kb: attribute each session to the KB found under its own working folder
    parts = [quoted(choice.python), "-I", "-B", quoted(layout.runner / "hook_ingest.py"), "--client", client,
             "--db", quoted(choice.ledger), "--log", quoted(choice.log), "--find-kb"]
    if posix(choice.adapter_python) != posix(choice.python):
        parts += ["--python", quoted(choice.adapter_python)]
    return " ".join(parts)


def wanted(layout, choice, client):
    """{event: [command]} mem-stats wants in this client's settings."""
    if client not in choice.clients:
        return {}
    line = hook_command(layout, choice, client)
    return {event: [line] for event in EVENTS[client]}


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}


def ours(hook):
    return isinstance(hook, dict) and bool(MARK.search(hook.get("command") or ""))


def strip(settings):
    """Remove mem-stats's hook commands one by one: another tool's command in the same group stays, and only a group
    left with no command goes."""
    hooks = settings.get("hooks") or {}
    for event in list(hooks):
        groups = []
        for group in hooks[event]:
            commands = group.get("hooks") if isinstance(group, dict) else None
            if isinstance(commands, list) and any(ours(h) for h in commands):
                kept = [h for h in commands if not ours(h)]
                if not kept:
                    continue
                group = {**group, "hooks": kept}
            groups.append(group)
        hooks[event] = groups
        if not hooks[event]:
            del hooks[event]
    if "hooks" in settings and not hooks:
        del settings["hooks"]
    return settings


def merged(settings, want):
    settings = strip(json.loads(json.dumps(settings)))
    hooks = settings.setdefault("hooks", {})
    for event, lines in want.items():
        for line in lines:
            hooks.setdefault(event, []).append({"hooks": [{"type": "command", "command": line}]})
    if not hooks:
        del settings["hooks"]
    return settings


def read_log(layout):
    log = load(layout.setup_log)
    return log if isinstance(log, dict) else {}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".mem-stats.tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def plan(layout, choice):
    changes = []
    for client in layout.clients:
        path, want = layout.settings(client), wanted(layout, choice, client)
        before = load(path)
        after = merged(before, want)
        if after != before:
            changes.append({"client": client, "file": posix(path), "before": before, "after": after, "want": want})
    copies = [(layout.extension / "runner" / name, layout.runner / name) for name in RUNNERS] if choice.clients else []
    return changes, copies


def describe(choice, changes, copies):
    lines = []
    if choice.clients:
        lines.append("ledger: %s (created by stats.py init if missing); run log: %s (counts only, never content)"
                     % (posix(choice.ledger), posix(choice.log)))
    for change in changes:
        lines.append("%s: %s" % (CLIENT_NAMES[change["client"]], change["file"]))
        for event, commands in change["want"].items():
            for line in commands:
                lines.append("  hook %s: %s" % (event, line))
        if not change["want"]:
            lines.append("  remove mem-stats's entries")
        elif change["client"] == "codex":
            lines.append("  then approve the new hook in Codex: /hooks in the CLI, or the app's hook review "
                         "(Codex runs a new or changed hook only once it is trusted)")
            lines.append("  Codex in the VS Code extension on Windows runs no hooks yet (openai/codex#33413): ingest "
                         "there with codex.py by hand")
    for source, target in copies:
        lines.append("copy %s -> %s" % (posix(source), posix(target)))
    if choice.backfill and choice.clients:
        lines.append("backfill now: every %s session on this host (may take a while)"
                     % " and ".join(CLIENT_NAMES[c] for c in choice.clients))
    return "\n".join(lines) or "nothing to change"


def run(command):
    hidden = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}  # no console window flashes
    result = subprocess.run([str(c) for c in command], stdin=subprocess.DEVNULL, capture_output=True, **hidden)
    last = (result.stderr.decode("utf-8", "replace").strip().splitlines() or [""])[-1]
    outcome = {"exit": result.returncode}
    try:
        summary = json.loads(last)
        outcome.update({k: summary[k] for k in ("inserted", "files", "sessions", "compressed_skipped")
                        if isinstance(summary.get(k), int)})
    except ValueError:
        if result.returncode:
            outcome["error"] = last[:300]
    return outcome


def hold(lock):
    """Take the hook's lock the way its worker does (exclusive create), waiting while a worker holds it; a stale lock,
    left by a worker that died, is taken over. Returns the token written into it."""
    token, waited = json.dumps({"pid": os.getpid(), "backfill": True, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}), False
    while True:
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                stale = time.time() - lock.stat().st_mtime >= STALE
            except OSError:
                continue  # released meanwhile
            if stale:
                try:
                    lock.unlink()
                except OSError:
                    pass
                continue
            if not waited:
                sys.stderr.write("backfill: waiting for the running ingestion to finish...\n")
                sys.stderr.flush()
                waited = True
            time.sleep(1)
            continue
        os.write(handle, token.encode("utf-8"))
        os.close(handle)
        return token


def keep_fresh(lock, stop):
    """Touch the lock while the backfill runs, so a hook never mistakes a long import for a dead worker."""
    while not stop.wait(60):
        try:
            os.utime(lock)
        except OSError:
            pass


def backfill(layout, choice):
    """Ingest the host's history once, holding the hook's lock so turns ending meanwhile queue instead. Progress goes
    to stderr."""
    results = {}
    lock = choice.ledger.with_name(choice.ledger.name + ".ingest.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    token, stop = hold(lock), threading.Event()
    threading.Thread(target=keep_fresh, args=(lock, stop), daemon=True).start()
    try:
        for client in choice.clients:
            sys.stderr.write("backfill: %s...\n" % CLIENT_NAMES[client])
            sys.stderr.flush()
            started = time.monotonic()
            results[client] = run([choice.adapter_python, "-I", "-B", layout.runner / ADAPTERS[client], "--all",
                                   "--db", choice.ledger] + (["--find-kb"] if client == "claude" else []))
            results[client]["seconds"] = round(time.monotonic() - started, 1)
            sys.stderr.write("  %s\n" % json.dumps(results[client], sort_keys=True))
    finally:
        stop.set()
        try:  # only our own lock: never one a worker took over
            if lock.read_text(encoding="utf-8") == token:
                lock.unlink()
        except OSError:
            pass
    return results


def apply(layout, choice):
    changes, copies = plan(layout, choice)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log = read_log(layout)
    for source, target in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    output = {"applied": []}
    if choice.clients:
        layout.state.mkdir(parents=True, exist_ok=True)
        init = run([choice.python, "-I", "-B", layout.runner / "stats.py", "--db", choice.ledger, "init"])
        if init["exit"]:
            raise SystemExit("stats.py init failed: " + json.dumps(init))
        output["ledger"] = posix(choice.ledger)
    files = log.setdefault("files", {})
    for change in changes:
        path = Path(change["file"])
        backup = layout.backups / stamp / (change["client"] + "-" + path.name)
        existed = path.exists()
        if existed:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
        write_json(path, change["after"])
        if change["want"]:
            files[change["file"]] = {"client": change["client"], "applied": stamp,
                                     "backup": posix(backup) if existed else None}
        else:
            files.pop(change["file"], None)
        output["applied"].append(change["file"])
    log.update(clients=choice.clients, applied=stamp)
    if choice.clients:
        log.update(ledger=posix(choice.ledger), log=posix(choice.log))
    write_json(layout.setup_log, log)
    if choice.backfill and choice.clients:
        output["backfill"] = backfill(layout, choice)
    return output


def ledger_files(ledger):
    ledger = Path(ledger)
    return [ledger] + [ledger.with_name(ledger.name + s) for s in ("-wal", "-shm", "-journal", ".ingest.lock")]


def reset(layout, delete_ledger=False):
    log, changed = read_log(layout), []
    for client in layout.clients:
        path = layout.settings(client)
        before = load(path)
        after = strip(json.loads(json.dumps(before)))
        if after != before:
            write_json(path, after)
            changed.append(posix(path))
        (log.get("files") or {}).pop(posix(path), None)
    output = {"reset": changed}
    if delete_ledger and log.get("ledger"):
        ledger = Path(log["ledger"])
        output["deleted"] = [posix(p) for p in ledger_files(ledger) if p.is_file()]
        for name in output["deleted"]:
            Path(name).unlink()
        shutil.rmtree(ledger.with_name(ledger.name + ".ingest-queue"), ignore_errors=True)
        log.pop("ledger", None)
    if layout.setup_log.exists():
        write_json(layout.setup_log, log)
    return output


def last_run(path):
    """The latest worker run in the log (lines carrying an exit code), and the latest error."""
    found = {"last_run": None, "last_error": None}
    try:
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if "exit" in entry:
                    found["last_run"] = entry
                if entry.get("exit") or entry.get("error") or str(entry.get("decision", "")).startswith(
                        ("error", "worker error")):
                    found["last_error"] = entry
    except OSError:
        pass
    return found


def status(layout):
    log, report = read_log(layout), {}
    for client in layout.clients:
        path = layout.settings(client)
        report[client] = {"file": posix(path), "hooks": [
            event + ": " + h.get("command") for event, groups in (load(path).get("hooks") or {}).items()
            for g in groups for h in g.get("hooks") or [] if ours(h)]}
    if log.get("ledger"):
        ledger = Path(log["ledger"])
        lock = ledger.with_name(ledger.name + ".ingest.lock")
        queue = ledger.with_name(ledger.name + ".ingest-queue")
        report["ledger"] = {"path": posix(ledger), "exists": ledger.is_file(),
                            "bytes": sum(p.stat().st_size for p in ledger_files(ledger)[:3] if p.is_file())}
        report["lock"] = ({"present": True, "age_seconds": round(time.time() - lock.stat().st_mtime)}
                          if lock.is_file() else {"present": False})
        report["queued"] = len(list(queue.glob("*.json"))) if queue.is_dir() else 0
    report["clients"] = log.get("clients")
    if log.get("log"):
        report["log"] = log["log"]
        report.update(last_run(log["log"]))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("plan", "apply", "reset", "status"))
    parser.add_argument("--answers", type=Path, help="the setup answers (plan, apply)")
    parser.add_argument("--extension-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--home", default="~", help="user home (tests)")
    parser.add_argument("--python", default=sys.executable, help="interpreter the hooks run with")
    parser.add_argument("--client", choices=CLIENTS, help="touch only this client's files (default: both)")
    parser.add_argument("--delete-ledger", action="store_true", help="reset: also delete the ledger")
    parser.add_argument("--json", action="store_true", help="machine-readable plan")
    args = parser.parse_args()
    layout = Layout(args)
    if args.action in ("plan", "apply"):
        if args.answers is None:
            parser.error(args.action + " needs --answers")
        choice = Choice(json.loads(args.answers.read_text(encoding="utf-8-sig")), layout)
        if args.action == "plan":
            changes, copies = plan(layout, choice)
            output = ({"changes": changes, "copies": [[posix(s), posix(t)] for s, t in copies],
                       "ledger": posix(choice.ledger)} if args.json else describe(choice, changes, copies))
        else:
            output = apply(layout, choice)
    elif args.action == "reset":
        output = reset(layout, args.delete_ledger)
    else:
        output = status(layout)
    sys.stdout.write((output if isinstance(output, str) else json.dumps(output, indent=2, ensure_ascii=False)) + "\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
