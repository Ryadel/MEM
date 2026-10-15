"""Codex usage adapter. Reads local rollouts; emits mem-stats/1 usage and lifecycle (compaction) events.

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
import sqlite3
import sys
from pathlib import Path

SCHEMA = "mem-stats/1"
CLIENT = "codex"
TESTED_VERSIONS = ("0.162.", "0.163.")
USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens")

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
    if path.suffix == ".zst":
        if zstd is None:
            return None
        with zstd.open(path, "rb") as stream:
            return io.TextIOWrapper(stream, encoding="utf-8", errors="replace").readlines()
    with open(path, encoding="utf-8", errors="replace") as stream:
        return stream.readlines()


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


def parse(path, coverage, provider="openai", workspace=None):
    content = lines(path)
    if content is None:
        coverage["compressed_skipped"] += 1
        return
    meta, model, seen, total = {}, None, set(), None
    # Rollouts before token_usage_record carry only event_msg/token_count: a response is a change of the cumulative
    # total, its usage last_token_usage, its id the line's position (stable, since rollouts are append-only).
    records = any('"token_usage_record"' in line for line in content)
    for index, line in enumerate(content):
        try:
            record = json.loads(line)
        except ValueError:
            coverage["unreadable_lines"] += 1
            continue
        kind, payload = record.get("type"), record.get("payload") or {}
        if kind == "session_meta":
            meta = payload
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
        if request in seen:  # a resumed session can log the same response again, later: the first one counts
            coverage["duplicate_records"] += 1
            continue
        seen.add(request)
        version = meta.get("cli_version") or "unknown"
        coverage["versions"][version] = coverage["versions"].get(version, 0) + 1
        coverage["sessions"].add(session)
        coverage["requests_emitted"] += 1
        reasoning = usage.get("reasoning_output_tokens")
        yield {"schema": SCHEMA, "id": "usage:" + session + ":" + request, "session": session, "kind": "usage",
               "request_id": request, "provider": meta.get("model_provider") or provider,
               "model": model or "unknown", "at": record.get("timestamp"), "usage": counts,
               "usage_detail": {"cache_write_1h": 0},
               "reasoning_output_tokens": reasoning if type(reasoning) is int else None,  # part of output
               "tier": {"service_tier": None, "speed": None, "inference_geo": None}, "output_final": True,
               "client": {"name": CLIENT, "version": version, "entrypoint": meta.get("originator"),
                          "sidechain": meta.get("thread_source") == "subagent", "agent": None}}


def same_folder(left, right):
    if not left:
        return False
    return os.path.normcase(os.path.abspath(left)).rstrip("\\/") == os.path.normcase(os.path.abspath(right)).rstrip("\\/")


def new_coverage():
    return {"client": CLIENT, "tested_versions": [v + "x" for v in TESTED_VERSIONS], "files": 0,
            "files_other_workspace": 0, "compressed_skipped": 0, "zstd_available": zstd is not None,
            "sessions": set(), "requests_emitted": 0, "unrecognized_usage_lines": 0, "unreadable_lines": 0,
            "versions": {}, "lifecycle_events": 0, "duplicate_records": 0, "from_token_count": 0}


def finish(coverage):
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
        collector = module.Collector(args.db)
    coverage, inserted = new_coverage(), 0
    try:
        for path in files:
            if args.session and args.session not in path.name:
                continue
            coverage["files"] += 1
            for event in parse(path, coverage, args.provider, args.workspace):
                if collector:
                    inserted += collector.add(event)
                else:
                    sys.stdout.write(json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n")
    finally:
        if collector:
            collector.close()
    summary = finish(coverage)
    if collector:
        summary["inserted"] = inserted
    print(json.dumps(summary, sort_keys=True), file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
