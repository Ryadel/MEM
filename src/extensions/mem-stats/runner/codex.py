"""Codex usage adapter. Reads local rollouts; emits mem-stats/1 usage, lifecycle (compaction) and coverage events.

Rollouts live in $CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl (default ~/.codex) and archived_sessions/; Codex
recompresses rollouts older than seven days to .jsonl.zst, which needs Python 3.14+ (stdlib compression.zstd) and
is otherwise skipped and counted. One usage event per `token_usage_record` (one per model response); the parallel
`event_msg/token_count` repeats it and is ignored. The model comes from the latest `turn_context`. MEM attribution
and context composition are not produced for Codex yet.

Read-only, no network.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

SCHEMA = "mem-stats/1"
CLIENT = "codex"
TESTED_VERSIONS = ("0.162.", "0.163.")
USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens")
# Identifiers the ledger accepts (stats.NAME) and paths (stats.LABEL).
NAME = re.compile(r"[\w.:@/+<>\[\]-]{1,100}")
LABEL = re.compile(r"[^\x00-\x1f\x7f]{1,300}")
ROLLOUT_ID = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl(?:\.zst)?$")

try:
    from compression import zstd  # Python 3.14+
except ImportError:
    zstd = None


def codex_home():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def rollouts(home):
    found = []
    for folder in ("sessions", "archived_sessions"):
        base = home / folder
        if base.is_dir():
            found += sorted(base.rglob("rollout-*.jsonl")) + sorted(base.rglob("rollout-*.jsonl.zst"))
    return found


def lines(path):
    """A text stream over a rollout's lines (read lazily: rollouts reach gigabytes), or None when it is compressed and
    zstd is unavailable."""
    if path.suffix == ".zst":
        if zstd is None:
            return None
        return io.TextIOWrapper(zstd.open(path, "rb"), encoding="utf-8", errors="replace")
    return open(path, encoding="utf-8", errors="replace")


def usage_counts(usage):
    """Codex input_tokens already includes cached input; output_tokens includes reasoning."""
    if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in USAGE_KEYS):
        return None
    write = usage.get("cache_write_input_tokens")
    write = write if type(write) is int and write >= 0 else 0
    if usage["cached_input_tokens"] + write > usage["input_tokens"]:
        return None
    return {"input": usage["input_tokens"], "cached_input": usage["cached_input_tokens"], "cache_write": write,
            "output": usage["output_tokens"]}


def parse(path, coverage, provider="openai", workspace=None, seen=None):
    """Yield usage and lifecycle events of one rollout. seen (session -> response ids) spans the rollouts of a run, so
    a response re-logged in another file of the same session counts once too."""
    named = ROLLOUT_ID.search(path.name)
    if named:
        coverage["session_id"] = named[1]
    content = lines(path)
    if content is None:
        coverage["compressed_skipped"] += 1
        return
    seen = {} if seen is None else seen
    # Rollouts before token_usage_record carry only event_msg/token_count: a response is a change of the cumulative
    # total, its usage last_token_usage, its id the line's position (stable, since rollouts are append-only). A first
    # pass, without parsing, finds out which kind this rollout is.
    with content:
        records = any('"token_usage_record"' in line for line in content)
    with lines(path) as content:
        yield from records_of(content, coverage, provider, workspace, seen, records)


def records_of(content, coverage, provider, workspace, seen, records):
    meta, model, total = {}, None, None
    for index, line in enumerate(content):
        try:
            record = json.loads(line)
        except ValueError:
            coverage["unreadable_lines"] += 1
            continue
        if not isinstance(record, dict):
            coverage["unreadable_lines"] += 1
            continue
        if isinstance(record.get("timestamp"), str) and record["timestamp"] > coverage.get("last_at", ""):
            coverage["last_at"] = record["timestamp"]
        kind, payload = record.get("type"), record.get("payload") or {}
        if kind == "session_meta":
            meta = payload
            if isinstance(payload.get("id"), str):
                coverage["session_id"] = payload["id"]
            if workspace is not None and not same_folder(payload.get("cwd"), workspace):
                coverage["files_other_workspace"] += 1
                return
            continue
        if kind == "turn_context":
            model = payload.get("model") or model
            continue
        session = meta.get("id") or payload.get("session_id") or payload.get("thread_id")
        if kind == "compacted" and session and record.get("timestamp"):
            latest = (payload.get("latest_token_usage_record") or {}).get("usage") or {}
            coverage["lifecycle_events"] += 1
            # Older rollouts carry no window_id: the line's ordinal (or timestamp) identifies the compaction.
            window = payload.get("window_id") or "line-" + str(record.get("ordinal", record["timestamp"]))
            yield {"schema": SCHEMA, "id": "lifecycle:" + session + ":" + window,
                   "session": session, "kind": "lifecycle", "at": record["timestamp"], "event": "compaction",
                   "trigger": None, "tokens_before": latest.get("input_tokens") if type(latest.get("input_tokens"))
                   is int else None, "tokens_after": None, "duration_ms": None}
            continue
        if kind == "token_usage_record":
            usage, request = payload.get("usage"), payload.get("response_id")
        elif not records and kind == "event_msg" and payload.get("type") == "token_count" and payload.get("info"):
            info = payload["info"]
            if info.get("total_token_usage") == total:
                continue
            total = info.get("total_token_usage")
            usage, request = info.get("last_token_usage"), "line-" + str(record.get("ordinal", index))
            coverage["from_token_count"] += 1
        else:
            continue
        counts = usage_counts(usage)
        if counts is None or not session or not request:
            coverage["unrecognized_usage_lines"] += 1
            continue
        ids = seen.setdefault(session, set())
        if request in ids:  # a resumed session can log the same response again, later: the first one counts
            coverage["duplicate_records"] += 1
            continue
        ids.add(request)
        version = meta.get("cli_version") or "unknown"
        coverage["versions"][version] = coverage["versions"].get(version, 0) + 1
        coverage["sessions"].add(session)
        coverage["requests_emitted"] += 1
        reasoning = usage.get("reasoning_output_tokens")
        event = {"schema": SCHEMA, "id": "usage:" + session + ":" + request, "session": session, "kind": "usage",
               "request_id": request, "provider": safe(meta.get("model_provider") or provider),
               "model": safe(model), "at": record.get("timestamp"), "usage": counts,
               "usage_detail": {"cache_write_1h": 0},
               "reasoning_output_tokens": reasoning if type(reasoning) is int else None,  # part of output
               "tier": {"service_tier": None, "speed": None, "inference_geo": None}, "output_final": True,
               "client": {"name": CLIENT, "version": safe(version), "entrypoint": safe(meta.get("originator"), None),
                          "sidechain": meta.get("thread_source") == "subagent", "agent": None}}
        project = project_path(meta.get("cwd"))
        if project:
            event["project"] = project  # the session's starting folder
        yield event


def project_path(folder):
    """A session's project folder, normalised: absolute, forward slashes, no trailing slash, lower-case drive letter
    (the rest keeps its case; comparisons ignore case on Windows). None when absent or not storable."""
    if not isinstance(folder, str) or not folder.strip():
        return None
    text = os.path.abspath(folder.strip()).replace("\\", "/")
    if re.match(r"[A-Za-z]:", text):
        text = text[0].lower() + text[1:]
    text = text.rstrip("/") or "/"
    if re.fullmatch(r"[a-z]:", text):
        text += "/"
    return text if LABEL.fullmatch(text) else None


def safe(name, fallback="unknown"):
    return name if isinstance(name, str) and NAME.fullmatch(name) else fallback


def same_folder(left, right):
    if not left:
        return False
    return os.path.normcase(os.path.abspath(left)).rstrip("\\/") == os.path.normcase(os.path.abspath(right)).rstrip("\\/")


def new_coverage():
    return {"client": CLIENT, "tested_versions": [v + "x" for v in TESTED_VERSIONS], "files": 0,
            "files_other_workspace": 0, "compressed_skipped": 0, "zstd_available": zstd is not None,
            "sessions": set(), "requests_emitted": 0, "unrecognized_usage_lines": 0, "unreadable_lines": 0,
            "versions": {}, "lifecycle_events": 0, "duplicate_records": 0, "from_token_count": 0, "conflicts": 0}


def merge(total, part):
    """Add one rollout's coverage counters to a running total."""
    for key, value in part.items():
        if type(value) is int:
            total[key] = total.get(key, 0) + value
        elif isinstance(value, set):
            total.setdefault(key, set()).update(value)
        elif isinstance(value, dict):
            merge(total.setdefault(key, {}), value)
        elif key == "last_at":
            total[key] = max(total.get(key) or "", value)
        else:
            total.setdefault(key, value)
    return total


def coverage_event(session, part):
    """A session's coverage counts as a ledger event: counts only, replaced by the next run over the session."""
    event = {"schema": SCHEMA, "id": "coverage:" + session + ":" + CLIENT, "session": session, "kind": "coverage",
             "client": CLIENT, "counts": {k: v for k, v in sorted(part.items()) if type(v) is int},
             "untested_versions": {safe(v): n for v, n in sorted(part["versions"].items())
                                   if not v.startswith(TESTED_VERSIONS)}}
    if part.get("last_at"):
        event["at"] = part["last_at"]
    return event


def finish(coverage):
    coverage.pop("session_id", None)
    coverage.pop("last_at", None)
    coverage["sessions"] = len(coverage["sessions"])
    coverage["untested_versions"] = sorted(v for v in coverage["versions"] if not v.startswith(TESTED_VERSIONS))
    return coverage


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--workspace", type=Path, help="only sessions whose working folder is this one")
    source.add_argument("--rollout", type=Path, action="append", help="explicit rollout file; repeatable")
    source.add_argument("--all", action="store_true", help="every rollout under the Codex home")
    parser.add_argument("--codex-home", type=Path, help="default: $CODEX_HOME or ~/.codex")
    parser.add_argument("--session", help="only this session (thread) id")
    parser.add_argument("--provider", default="openai", help="provider label when the rollout names none")
    parser.add_argument("--db", type=Path, help="ingest into this mem-stats ledger instead of writing JSONL to stdout")
    args = parser.parse_args()
    files = args.rollout or rollouts(args.codex_home or codex_home())
    collector = None
    if args.db:
        import importlib.util
        spec = importlib.util.spec_from_file_location("mem_stats", Path(__file__).with_name("stats.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        collector = module.Collector(args.db, batch=module.BATCH)
    coverage, sessions, seen = new_coverage(), {}, {}

    def deliver(event, part):
        if collector:
            part["conflicts"] += collector.offer(event) == "conflict"
        else:
            sys.stdout.write(json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n")
    try:
        for path in files:
            if args.session and args.session not in path.name:
                continue
            part = new_coverage()
            part["files"] = 1
            for event in parse(path, part, args.provider, args.workspace, seen):
                deliver(event, part)
            if part.get("session_id") and not part["files_other_workspace"]:
                merge(sessions.setdefault(part["session_id"], {}), part)
            merge(coverage, part)
        for session, part in sessions.items():  # one coverage event per session, after all its rollouts
            deliver(coverage_event(session, part), coverage)
    finally:
        if collector:
            collector.close()
    summary = finish(coverage)
    if collector:
        for key in ("inserted", "replaced", "unchanged", "kept"):
            summary[key] = collector.outcomes[key]
    print(json.dumps(summary, sort_keys=True), file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
