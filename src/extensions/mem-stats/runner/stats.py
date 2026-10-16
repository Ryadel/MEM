"""Local event collector. No model calls, hooks, network traffic or mem-optimize dependency."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import statistics
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

VERSION = "0.1.1"
RARELY = 1000  # a loaded tool called at most once per this many requests carrying it is "rarely called"
SCHEMA = "mem-stats/1"
LIFECYCLE = ("compaction", "clear")
BUCKETS = ("input", "cached_input", "cache_write", "output")
# Pricing tier attributes and the value assumed when an event or price card omits one.
TIER = {"service_tier": "standard", "speed": "standard", "inference_geo": "global"}
# A later request writing at least this share of a prompt at least this large rewrote the cache: a cache break.
BREAK_SHARE, BREAK_MIN = 0.5, 10_000
# Batched writers (adapters, INGEST) commit every BATCH events or BATCH_SECONDS, whichever comes first, so a long
# backfill neither pays one disk sync per event nor keeps other writers waiting for long.
BATCH, BATCH_SECONDS = 1000, 2.0

# Closed schema. The ledger holds counts and identifiers, never content: every kind accepts a fixed set of keys,
# identifiers are short and free of spaces and control characters, and only KB page and file paths may carry spaces.
NAME = re.compile(r"[\w.:@/+<>\[\]-]+")
LABEL = re.compile(r"[^\x00-\x1f\x7f]+")
EXTENSION_ID = re.compile(r"[a-z][a-z0-9-]{0,63}")
METRIC_NAME = re.compile(r"[a-z][a-z0-9-]{0,63}\.[a-z0-9_]+(?:\.[a-z0-9_]+)*")
UNITS = ("count", "tokens", "requests", "seconds", "milliseconds", "bytes", "percent", "usd", "eur")
ENVELOPE = ("schema", "id", "session", "kind", "at")
FIELDS = {
    "usage": ("request_id", "provider", "model", "usage", "usage_detail", "tier", "server_tool_use", "output_final",
              "client", "mem", "extensions", "reasoning_output_tokens", "project"),
    "attribution": ("request_id", "method", "count_method", "mem", "extensions", "categories", "kb_roots"),
    "composition": ("request_id", "method", "count_method", "sources", "processed"),
    "breakdown": ("request_id", "method", "count_method", "overhead", "tools_called", "prefix", "kb_pages", "kb_roots"),
    "overhead": ("source", "count_method", "items"),
    "inventory": ("snapshot",),
    "delivery": ("source_extension", "processor_extension", "path", "raw_tokens", "presented_tokens", "count_method"),
    "lifecycle": ("event", "trigger", "tokens_before", "tokens_after", "duration_ms"),
    "coverage": ("client", "counts", "untested_versions", "context"),
    "metric": ("extension", "name", "version", "value", "unit"),
}
CLIENT_FIELDS = ("name", "version", "entrypoint", "sidechain", "agent", "agent_type")
SNAPSHOT_FIELDS = ("extensions_enabled", "catalog_coverage", "catalog_sha256", "registry_sha256", "extensions")
INVENTORY_FIELDS = ("id", "configured_status", "effective_active", "reason", "installed_version", "registered_version",
                    "catalog_version", "in_catalog", "installed", "executable_content", "execution_allowed")
# Estimates checked against the usage event of their request.
DEPENDENT = ("attribution", "composition", "breakdown")
# Measured kinds: a re-sent event must agree on these fields; other kinds are derived, and the latest one wins.
MEASURED = {"usage": ("provider", "model", "request_id", "usage", "usage_detail", "server_tool_use",
                      "reasoning_output_tokens", "output_final"),
            "delivery": ("source_extension", "processor_extension", "path", "raw_tokens", "presented_tokens")}
SECTIONS = ("provider_usage", "projects", "mem_attribution", "money", "context_composition", "fixed_overhead", "kb_pages",
            "cache_breaks", "costliest", "lifecycle", "subagents", "coverage", "extension_metrics", "extensions",
            "payload", "inventory_by_session")


class Conflict(ValueError):
    """A measured event re-sent with different counts under an existing id."""


def token_count(text, encoding=None):
    if encoding:
        import tiktoken
        return len(tiktoken.get_encoding(encoding).encode(text, disallowed_special=())), "tokenized:" + encoding
    return math.ceil(len(text) / 4), "estimated:characters/4"


def checked_path(root, relative):
    root = Path(root).resolve(strict=True)
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("file must resolve inside KB_ROOT")
    return path


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError("token counts must be non-negative integers")
    return value


def buckets(value):
    if not isinstance(value, dict) or set(value) != set(BUCKETS):
        raise ValueError("counts require input, cached_input, cache_write and output")
    result = {key: integer(value[key]) for key in BUCKETS}
    if result["cached_input"] + result["cache_write"] > result["input"]:
        raise ValueError("cached input plus cache writes exceed input")
    return result


def portions(value):
    return (value["input"] - value["cached_input"] - value["cache_write"],
            value["cached_input"], value["cache_write"], value["output"])


def subset(child, parent):
    if any(a > b for a, b in zip(portions(child), portions(parent))):
        raise ValueError("attributed counts exceed their corresponding usage buckets")


def moment(value):
    """An ISO date or date/time as an aware UTC datetime (naive values are UTC); None when absent."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("times must be ISO dates or date/times")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        raise ValueError("times must be ISO dates or date/times") from None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def when(event):
    try:
        return moment(event.get("at"))
    except ValueError:
        return None


def name(value, what, optional=False, limit=128, pattern=NAME):
    if value is None and optional:
        return None
    if not isinstance(value, str) or len(value) > limit or not pattern.fullmatch(value):
        raise ValueError(what + " must be an identifier of at most " + str(limit) + " characters")
    return value


def label(value, what, optional=False):
    return name(value, what, optional, 300, LABEL)


def closed(value, allowed, what):
    if not isinstance(value, dict):
        raise ValueError(what + " must be an object")
    unknown = sorted(str(k)[:40] for k in set(value) - set(allowed))
    if unknown:
        raise ValueError(what + " does not accept: " + ", ".join(unknown))
    return value


def tally(value, what, key=name):
    """A map of identifiers to non-negative integer counts."""
    if not isinstance(value, dict):
        raise ValueError(what + " must map names to counts")
    for k, v in value.items():
        key(k, what + " keys")
        integer(v)
    return value


def split(value, what, fields, key=name):
    """A map of identifiers to {field: count} with exactly these fields."""
    if not isinstance(value, dict) or any(not isinstance(v, dict) or set(v) != set(fields) for v in value.values()):
        raise ValueError(what + " needs " + "/".join(fields) + " counts")
    for k, v in value.items():
        key(k, what + " keys")
        for field in fields:
            integer(v[field])
    return value


def optional_integer(event, *keys):
    for key in keys:
        if event.get(key) is not None:
            integer(event[key])


def validate(event):
    """Check an event against the closed schema of its kind; returns the kind."""
    if not isinstance(event, dict) or event.get("schema") != SCHEMA:
        raise ValueError("event schema must be " + SCHEMA)
    for key in ("id", "session", "kind"):
        if not isinstance(event.get(key), str) or not event[key].strip():
            raise ValueError("event requires " + key)
    kind = event["kind"]
    if kind not in FIELDS:
        raise ValueError("unsupported event kind")
    closed(event, ENVELOPE + FIELDS[kind], kind)
    name(event["id"], "id", limit=256)
    name(event["session"], "session")
    moment(event.get("at"))
    prefix = kind + ":" + event["session"] + ":"
    if kind == "usage":
        total = buckets(event.get("usage"))
        if not all(isinstance(event.get(k), str) and event[k] for k in ("provider", "model", "request_id")):
            raise ValueError("usage requires provider, model and request_id")
        for key in ("provider", "model", "request_id"):
            name(event[key], key)
        if event["id"] != "usage:" + event["session"] + ":" + event["request_id"]:
            raise ValueError("usage id must be usage:<session>:<request_id>")
        mem = buckets(event["mem"]) if event.get("mem") is not None else None
        if mem:
            subset(mem, total)
        if not isinstance(event.get("extensions", {}), dict):
            raise ValueError("extensions must map extension ids to counts")
        allocated = [buckets(v) for v in event.get("extensions", {}).values()]
        for key in event.get("extensions", {}):
            name(key, "extension ids")
        subset({k: sum(v[k] for v in allocated) for k in BUCKETS}, mem if mem is not None else total)
        detail = event.get("usage_detail")
        if detail is not None:
            if not isinstance(detail, dict) or set(detail) - {"cache_write_1h"}:
                raise ValueError("usage_detail supports cache_write_1h only")
            if integer(detail.get("cache_write_1h", 0)) > total["cache_write"]:
                raise ValueError("cache_write_1h exceeds cache_write")
        tier = event.get("tier")
        if tier is not None and (not isinstance(tier, dict) or set(tier) - set(TIER)
                                 or any(v is not None and not isinstance(v, str) for v in tier.values())):
            raise ValueError("tier supports service_tier, speed and inference_geo strings")
        for value in (tier or {}).values():
            name(value, "tier values", optional=True)
        tally(event.get("server_tool_use", {}), "server_tool_use")
        if "output_final" in event and type(event["output_final"]) is not bool:
            raise ValueError("output_final must be a boolean")
        optional_integer(event, "reasoning_output_tokens")
        label(event.get("project"), "project", optional=True)
        client = event.get("client")
        if client is not None:
            closed(client, CLIENT_FIELDS, "client")
            for key in ("name", "version", "entrypoint", "agent", "agent_type"):
                name(client.get(key), "client " + key, optional=True)
            if client.get("sidechain") is not None and type(client["sidechain"]) is not bool:
                raise ValueError("client sidechain must be a boolean")
    elif kind in DEPENDENT:
        required = ("request_id", "method", "count_method") if kind == "attribution" else ("request_id", "method")
        if not all(isinstance(event.get(k), str) and event[k] for k in required):
            raise ValueError(kind + " requires " + ", ".join(required[:-1]) + " and " + required[-1])
        for key in ("request_id", "method"):
            name(event[key], key)
        name(event.get("count_method"), "count_method", optional=kind != "attribution")
        if event["id"] != prefix + event["request_id"] + ":" + event["method"]:
            raise ValueError(kind + " id must be " + kind + ":<session>:<request_id>:<method>")
        optional_integer(event, "kb_roots")
        if kind == "attribution":
            buckets(event.get("mem"))
            if not isinstance(event.get("extensions", {}), dict):
                raise ValueError("extensions must map extension ids to counts")
            for key, value in event.get("extensions", {}).items():
                name(key, "extension ids")
                buckets(value)
            tally(event.get("categories", {}), "attribution categories")
        elif kind == "composition":
            try:
                split(event.get("sources"), "composition sources", ("new", "carried"))
                split(event.get("processed", {}), "composition processed", ("results", "new", "carried"))
            except ValueError:
                raise ValueError("composition sources need new/carried counts; processed adds results") from None
        else:
            try:
                split(event.get("kb_pages", {}), "kb_pages", ("new", "carried"), key=label)
                tally(event.get("tools_called", {}), "tools_called")
                overhead = event.get("overhead", [])
                if not isinstance(overhead, list):
                    raise ValueError("overhead must be a list")
                for item in overhead:
                    name(item, "overhead ids", limit=256)
            except ValueError:
                raise ValueError("breakdown needs kb_pages new/carried counts, tools_called counts and "
                                 "overhead ids") from None
            optional_integer(event, "prefix")
    elif kind == "overhead":
        items = event.get("items")
        if not isinstance(event.get("source"), str) or not event["source"] or not isinstance(items, dict) or not items:
            raise ValueError("overhead requires a source and token counts by item")
        name(event["source"], "overhead source")
        name(event.get("count_method"), "count_method", optional=True)
        tally(items, "overhead items")
    elif kind == "inventory":
        snapshot = event.get("snapshot")
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("extensions"), list):
            raise ValueError("inventory requires an extension snapshot")
        closed(snapshot, SNAPSHOT_FIELDS, "inventory snapshot")
        if snapshot.get("extensions_enabled") is not None and type(snapshot["extensions_enabled"]) is not bool:
            raise ValueError("inventory extensions_enabled must be a boolean")
        for key in ("catalog_coverage", "catalog_sha256", "registry_sha256"):
            name(snapshot.get(key), "inventory " + key, optional=True)
        for entry in snapshot["extensions"]:
            closed(entry, INVENTORY_FIELDS, "inventory entry")
            for key, value in entry.items():
                if value is not None and type(value) is not bool:
                    name(value, "inventory " + key)
    elif kind == "delivery":
        for key in ("raw_tokens", "presented_tokens"):
            integer(event.get(key))
        if not event.get("count_method"):
            raise ValueError("delivery requires count_method")
        if not isinstance(event.get("source_extension"), str):
            raise ValueError("delivery requires source_extension")
        name(event["count_method"], "count_method")
        name(event["source_extension"], "source_extension")
        name(event.get("processor_extension"), "processor_extension", optional=True)
        label(event.get("path"), "path", optional=True)
    elif kind == "lifecycle":
        if event.get("event") not in LIFECYCLE or not isinstance(event.get("at"), str) or not event["at"]:
            raise ValueError("lifecycle requires event (" + ", ".join(LIFECYCLE) + ") and at")
        name(event.get("trigger"), "trigger", optional=True)
        optional_integer(event, "tokens_before", "tokens_after", "duration_ms")
    elif kind == "coverage":
        name(event.get("client"), "coverage client")
        if event["id"] != prefix + event["client"]:
            raise ValueError("coverage id must be coverage:<session>:<client>")
        tally(event.get("counts"), "coverage counts")
        tally(event.get("untested_versions", {}), "coverage untested_versions")
        tally(event.get("context", {}), "coverage context")
    elif kind == "metric":
        extension = name(event.get("extension"), "metric extension", limit=64, pattern=EXTENSION_ID)
        metric = name(event.get("name"), "metric name", pattern=METRIC_NAME)
        if not metric.startswith(extension + "."):
            raise ValueError("metric name must be <extension-id>.<metric>")
        if not event["id"].startswith("metric:" + extension + ":"):
            raise ValueError("metric id must start with metric:<extension-id>:")
        if type(event.get("version")) is not int or event["version"] < 1:
            raise ValueError("metric version must be a positive integer")
        value = event.get("value")
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("metric value must be a finite number")
        if event.get("unit") is not None and event["unit"] not in UNITS:
            raise ValueError("metric unit must be one of " + ", ".join(UNITS))
    return kind


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


def under(project, root):
    """True when a project folder is root or lies under it; case-insensitive on Windows paths."""
    if not project or not root:
        return False
    if os.name == "nt" or re.match(r"[a-z]:/", root):
        project, root = project.casefold(), root.casefold()
    return project == root or project.startswith(root.rstrip("/") + "/")


def less_context(stored, new):
    """True when a derived event was computed with less context than the stored one, which then stays.

    The rule: a run that knew fewer KB roots (`kb_roots`) must not overwrite estimates made with more, and, for events
    stored before `kb_roots` was recorded, a breakdown without KB pages must not blank one that has them (typically a
    host-wide run without --kb-root after a workspace run). Otherwise the latest derived event wins."""
    if isinstance(stored.get("kb_roots"), int) and isinstance(new.get("kb_roots"), int):
        return new["kb_roots"] < stored["kb_roots"]
    return bool(stored.get("kb_pages")) and not new.get("kb_pages")


def dumps(event):
    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def metadata(text):
    result = {}
    for line in text.splitlines():
        match = re.match(r"\s*-\s+\*\*([^*]+)\*\*:\s*(.*)", line)
        if match:
            result[match[1].lower()] = match[2].strip().strip("`")
    return result


def entries(text):
    return {m[1]: metadata(m[2]) for m in re.finditer(
        r"^###\s+([a-z][a-z0-9-]*)\s*\n(.*?)(?=^###\s|\Z)", text, re.M | re.S)}


def registry(root):
    """(sha256, latest mtime) of the files that decide extension states: extensions/EXT.md and MEM.config.md."""
    digest, latest = hashlib.sha256(), None
    for path in (Path(root) / "extensions" / "EXT.md", Path(root) / "MEM.config.md"):
        if path.is_file():
            digest.update(path.read_bytes())
            changed = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            latest = max(latest, changed) if latest else changed
        digest.update(b"\0")
    return digest.hexdigest(), latest


def inventory(root, manifest=None):
    root = Path(root).resolve(strict=True)
    config = root / "MEM.config.md"
    enabled = not (config.exists() and re.search(
        r"^extensions_enabled:\s*false\s*(?:#.*)?$", config.read_text(encoding="utf-8-sig"), re.M))
    executable_allowed = bool(config.exists() and re.search(
        r"^extensions_allow_executable_content:\s*true\s*(?:#.*)?$", config.read_text(encoding="utf-8-sig"), re.M))
    ext = root / "extensions"
    registration = ext / "EXT.md"
    registered = entries(registration.read_text(encoding="utf-8-sig")) if registration.exists() else {}
    catalog = entries(Path(manifest).read_text(encoding="utf-8-sig")) if manifest else {}
    installed = {p.parent.name for p in ext.glob("*/index.md")} if ext.exists() else set()
    result = []
    for key in sorted(set(registered) | set(catalog) | installed):
        record = registered.get(key, {})
        status = record.get("status", "unregistered" if key in installed else "not-installed")
        custom_path = record.get("path", "extensions/" + key + "/index.md")
        present = False
        entrypoint = None
        try:
            entrypoint = checked_path(root, custom_path)
            present = True
        except (ValueError, OSError):
            pass
        effective = enabled and status == "active" and present
        installed_metadata = metadata(entrypoint.read_text(encoding="utf-8-sig")) if entrypoint else {}
        version = installed_metadata.get("version")
        has_executable = bool(re.search(r"\byes\b", record.get("executable content", installed_metadata.get("executable content", "no")), re.I))
        result.append({"id": key, "configured_status": status, "effective_active": effective,
                       "reason": "active" if effective else "globally-disabled" if not enabled else
                       "missing-entrypoint" if status == "active" and not present else status,
                       "installed_version": version, "registered_version": record.get("version"),
                       "catalog_version": catalog.get(key, {}).get("version"),
                       "in_catalog": key in catalog, "installed": present,
                       "executable_content": has_executable, "execution_allowed": effective and (not has_executable or executable_allowed)})
    return {"extensions_enabled": enabled, "catalog_coverage": "supplied-catalog" if manifest else "local-only",
            "catalog_sha256": hashlib.sha256(Path(manifest).read_bytes()).hexdigest() if manifest else None,
            "registry_sha256": registry(root)[0], "extensions": result}


class Collector:
    def __init__(self, path, create=False, batch=0):
        """batch: commit every `batch` events (and at least every BATCH_SECONDS) instead of after each one; close()
        commits the rest. Outcomes and conflicts are per event either way."""
        self.path = Path(path).resolve()
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        elif not self.path.is_file():
            raise ValueError("stats is not initialized")
        self.db = sqlite3.connect(str(self.path), timeout=15)
        self.db.execute("PRAGMA busy_timeout=15000")
        self.db.execute("PRAGMA synchronous=NORMAL")  # with WAL: durable at checkpoints, never corrupt
        if create:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('schema', ?)", (SCHEMA,))
            self.db.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, session TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL)")
            self.db.commit()
        try:
            if self.db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone() != (SCHEMA,):
                raise ValueError("unsupported stats database schema")
        except (ValueError, sqlite3.Error):
            self.db.close()
            raise
        # Outcomes of add(): inserted, replaced, unchanged, kept; offer() adds conflicts and skipped.
        self.outcomes, self.last, self.conflicted = Counter(), None, set()
        self.batch, self.pending, self.opened = batch, 0, None

    def flush(self):
        """Commit the events written since the last commit."""
        self.db.commit()
        self.pending, self.opened = 0, None

    def close(self):
        try:
            self.flush()
        finally:
            self.db.close()

    def prune(self, before):
        """Delete whole sessions whose latest timed event is before `before`; never half a session. Overhead events
        still referenced by a kept breakdown stay. Sessions without any timed event have no known age and stay."""
        limit = moment(before)
        if limit is None:
            raise ValueError("prune requires --before")
        rows = self.db.execute("SELECT id, session, kind, payload FROM events").fetchall()
        latest, untimed = {}, set()
        for _, session, _, payload in rows:
            at = when(json.loads(payload))
            if at:
                latest[session] = max(latest.get(session, at), at)
            else:
                untimed.add(session)
        old = {s for s, at in latest.items() if at < limit}
        referenced = {key for _, session, kind, payload in rows if kind == "breakdown" and session not in old
                      for key in json.loads(payload).get("overhead", [])}
        doomed = [(i,) for i, session, kind, _ in rows if session in old and not (kind == "overhead" and i in referenced)]
        with self.db:
            self.db.executemany("DELETE FROM events WHERE id=?", doomed)
        self.db.execute("VACUUM")
        return {"before": before, "sessions_deleted": len(old), "events_deleted": len(doomed),
                "sessions_without_age": len(untimed - set(latest))}

    def add(self, event):
        """Validate and store one event; True when its id was new. A re-sent id follows store()'s rules."""
        kind = validate(event)
        if kind in DEPENDENT:
            row = self.db.execute("SELECT payload FROM events WHERE id=?",
                                  ("usage:" + event["session"] + ":" + event["request_id"],)).fetchone()
            if row is None:
                raise ValueError(kind + " requires its usage event")
            usage = json.loads(row[0])["usage"]
            if kind == "attribution":
                # An estimate kept apart from measured usage, so a better method can be added without conflicts.
                mem = buckets(event["mem"])
                subset(mem, usage)
                allocated = [buckets(v) for v in event.get("extensions", {}).values()]
                subset({k: sum(v[k] for v in allocated) for k in BUCKETS}, mem)
                if sum(event.get("categories", {}).values()) > mem["input"]:
                    raise ValueError("attribution categories must be input counts within mem input")
            elif kind == "composition":
                content = sum(v["new"] + v["carried"] for v in event["sources"].values())
                if content > usage["input"]:
                    raise ValueError("composition exceeds the request's input")
            elif event.get("prefix", 0) > usage["input"] or sum(
                    v["new"] + v["carried"] for v in event.get("kb_pages", {}).values()) > usage["input"]:
                raise ValueError("breakdown exceeds the request's input")
        status = self.store(event, kind, dumps(event))
        self.outcomes[status] += 1
        self.last = status
        return status == "inserted"

    def store(self, event, kind, payload):
        """write() inside the current transaction, committed per event or per batch."""
        try:
            status = self.write(event, kind, payload)
        except BaseException:
            if not self.batch:
                self.db.rollback()
            raise  # in a batch, a refused event has written nothing: the batch goes on
        self.pending += 1
        self.opened = self.opened or time.monotonic()
        if not self.batch or self.pending >= self.batch or time.monotonic() - self.opened >= BATCH_SECONDS:
            self.flush()
        return status

    def write(self, event, kind, payload):
        """Insert, or apply a re-sent id. Measured events (usage, delivery) must agree on every count and identity
        field: then the newer payload, merged over the stored one, replaces it (an adapter upgrade adding fields is
        accepted, a run omitting them loses nothing, and the earliest time is kept); disagreement raises Conflict.
        Derived events: the latest wins, unless it was computed with less context (less_context)."""
        if self.db.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?)",
                           (event["id"], event["session"], kind, payload)).rowcount:
            return "inserted"
        previous = self.db.execute("SELECT payload FROM events WHERE id=?", (event["id"],)).fetchone()[0]
        if previous == payload:
            return "unchanged"
        stored = json.loads(previous)
        if stored.get("kind") != kind or stored.get("session") != event["session"]:
            raise Conflict("event id already used by another kind or session")
        if kind in MEASURED:
            differing = [k for k in MEASURED[kind] if k in stored and k in event and stored[k] != event[k]]
            if differing:
                raise Conflict("conflicting " + ", ".join(differing) + " for an existing " + kind + " event")
            merged = {**stored, **event}
            times = [t for t in (stored.get("at"), event.get("at")) if t]
            if times:
                merged["at"] = min(times, key=moment)  # a response re-logged on resume keeps its first time
        elif less_context(stored, event):
            return "kept"
        else:
            merged = event
        payload = dumps(merged)
        if payload == previous:
            return "unchanged"
        # Delete and insert rather than update in place: the row takes a new rowid, so reports reading in rowid
        # order see it as the latest, and WATCH notices the change from max(rowid) and the last payload.
        self.db.execute("DELETE FROM events WHERE id=?", (event["id"],))
        self.db.execute("INSERT INTO events VALUES (?,?,?,?)", (event["id"], event["session"], kind, payload))
        return "replaced"

    def offer(self, event):
        """add() for adapters and INGEST: returns the outcome. A conflict is counted, not raised, and the estimates of
        the conflicting request are skipped, since they were computed on usage the ledger does not hold."""
        key = (event.get("session"), event.get("request_id")) if isinstance(event, dict) else None
        if isinstance(event, dict) and event.get("kind") in DEPENDENT and key in self.conflicted:
            self.outcomes["skipped"] += 1
            return "skipped"
        try:
            self.add(event)
        except Conflict:
            self.outcomes["conflicts"] += 1
            if event.get("kind") == "usage":
                self.conflicted.add(key)
            return "conflict"
        return self.last

    def report(self, session=None, prices=None, attribution_method=None, since=None, until=None, top=10, kb_root=None,
               project=None):
        rows = self.db.execute("SELECT payload FROM events" + (" WHERE session=?" if session else "") + " ORDER BY rowid",
                               (session,) if session else ()).fetchall()
        events = [json.loads(row[0]) for row in rows]
        if project:
            # A project is a session's starting folder: keep the requests made in it or under it, their estimates, and
            # the session-level events (lifecycle, coverage, inventory, overhead, metrics) of their sessions.
            root = project_path(project)
            kept = {(e["session"], e["request_id"]) for e in events
                    if e["kind"] == "usage" and under(e.get("project"), root)}
            sessions = {s for s, _ in kept}
            events = [e for e in events if ((e["session"], e.get("request_id")) in kept
                                            if e["kind"] in ("usage",) + DEPENDENT else e["session"] in sessions)]
        start, end = moment(since), moment(until)
        for card in prices or []:
            if moment(card.get("as_of")) is None:
                raise ValueError("price cards require as_of")
            if card.get("until") and moment(card["until"]) <= moment(card["as_of"]):
                raise ValueError("a price card's until must follow its as_of")
        if start or end:
            # A period keeps timed events within [since, until); estimates follow the usage they belong to, coverage
            # the sessions with requests in the period.
            def within(e):
                at = when(e)
                return at is not None and (not start or at >= start) and (not end or at < end)
            kept = {(e["session"], e["request_id"]) for e in events if e["kind"] == "usage" and within(e)}
            sessions = {s for s, _ in kept}
            events = [e for e in events if (e["session"], e.get("request_id")) in kept
                      if e["kind"] in ("usage",) + DEPENDENT] + [
                e for e in events if e["kind"] in ("delivery", "lifecycle", "metric") and within(e)] + [
                e for e in events if e["kind"] in ("inventory", "overhead")] + [
                e for e in events if e["kind"] == "coverage" and e["session"] in sessions]
        deliveries = [e for e in events if e["kind"] == "delivery"]
        # Inline attribution wins; otherwise the latest attribution event (of the chosen method) applies.
        estimates = {(e["session"], e["request_id"]): e for e in events if e["kind"] == "attribution"
                     and (attribution_method is None or e["method"] == attribution_method)}
        uses = []
        for e in events:
            if e["kind"] == "usage":
                estimate = estimates.get((e["session"], e["request_id"])) if e.get("mem") is None else None
                uses.append({**e, "mem": estimate["mem"], "extensions": estimate.get("extensions", {}),
                             "attribution": estimate} if estimate else e)
        categories = Counter()
        for e in uses:
            categories.update((e.get("attribution") or {}).get("categories", {}))
        covered = [e for e in uses if e.get("mem") is not None]
        raw = sum(e["raw_tokens"] for e in deliveries)
        presented = sum(e["presented_tokens"] for e in deliveries)
        total_input = sum(e["usage"]["input"] for e in covered)
        mem_input = sum(e["mem"]["input"] for e in covered)
        snapshots = [e for e in events if e["kind"] == "inventory"]
        # Across sessions, preserve one inventory per session; an active state in A says nothing about B.
        latest = {e["session"]: e["snapshot"] for e in snapshots}
        extension_ids = set(e["source_extension"] for e in deliveries) | set(
            e["processor_extension"] for e in deliveries if e.get("processor_extension")) | set(
            k for e in uses for k in e.get("extensions", {})) | set(
            x["id"] for snap in latest.values() for x in snap["extensions"])
        extension_stats = []
        for key in sorted(extension_ids):
            reads = [e for e in deliveries if e["source_extension"] == key]
            ext_uses = [e for e in uses if key in e.get("extensions", {})]
            extension_stats.append({"id": key, "deliveries": len(reads),
                                   "observed": bool(reads or ext_uses or any(e.get("processor_extension") == key for e in deliveries)),
                                   "states_by_session": {s: next(x for x in snap["extensions"] if x["id"] == key)
                                                         for s, snap in latest.items() if any(x["id"] == key for x in snap["extensions"])},
                                   "processing_deliveries": sum(e.get("processor_extension") == key for e in deliveries),
                                   "payload_tokens": sum(e["presented_tokens"] for e in reads),
                                   "compression_saved_tokens": sum(e["raw_tokens"] - e["presented_tokens"] for e in reads),
                                   "usage_requests_with_attribution": len(ext_uses),
                                   "usage_requests_without_attribution": len(uses) - len(ext_uses),
                                   "attributed_input_tokens": sum(e["extensions"][key]["input"] for e in ext_uses) if ext_uses else None,
                                   "attributed_output_tokens": sum(e["extensions"][key]["output"] for e in ext_uses) if ext_uses else None,
                                   "input_share_percent_on_attributed_requests": percent(sum(e["extensions"][key]["input"] for e in ext_uses),
                                       sum(e["usage"]["input"] for e in ext_uses)) if ext_uses else None})
        money, costs, unpriced, undated, backdated = {}, {}, Counter(), 0, Counter()
        for event in uses:
            card, reason = card_for(prices, event)
            if card is None:
                unpriced[reason] += 1
                continue
            total_cost = price(event["usage"], card, write_1h(event))
            if total_cost is None:
                unpriced["rate_missing"] += 1  # 1h cache writes need a rate the card lacks: unpriced, not zero
                continue
            undated += reason == "undated"
            if reason == "before_card_date":
                backdated[card_label(card)] += 1
            costs[(event["session"], event["request_id"])] = (card["currency"], total_cost)
            mem_cost = price(event["mem"], card, write_1h(event, event["mem"])) if event.get("mem") is not None else None
            item = money.setdefault(card["currency"], {"priced_requests": 0, "total": Decimal(0),
                         "mem_cost_covered_requests": 0, "mem_allocated": Decimal(0), "covered_total": Decimal(0)})
            item["priced_requests"] += 1
            item["total"] += total_cost
            if mem_cost is not None:
                item["mem_cost_covered_requests"] += 1
                item["mem_allocated"] += mem_cost
                item["covered_total"] += total_cost
            for extension in extension_stats:
                attributed = event.get("extensions", {}).get(extension["id"])
                amount = price(attributed, card, write_1h(event, attributed)) if attributed is not None else None
                if amount is not None:
                    costs_by = extension.setdefault("allocated_money", {})
                    values = costs_by.setdefault(card["currency"], {"requests": 0, "amount": Decimal(0)})
                    values["requests"] += 1
                    values["amount"] += amount
        for extension in extension_stats:
            for values in extension.get("allocated_money", {}).values():
                values["amount"] = str(values["amount"])
        for item in money.values():
            item["mem_share_percent_on_covered_requests"] = percent(item["mem_allocated"], item["covered_total"]) if item["mem_cost_covered_requests"] else None
            for key in ("total", "mem_allocated", "covered_total"):
                item[key] = str(item[key])
            if not item["mem_cost_covered_requests"]:
                item["mem_allocated"] = None
        # Context composition: where prompt tokens come from, and how much of it is carried from earlier requests.
        compositions = {(e["session"], e["request_id"]): e for e in events if e["kind"] == "composition"
                        and (attribution_method is None or e["method"] == attribution_method)}
        composed = [e for e in uses if (e["session"], e["request_id"]) in compositions]
        composed_input = sum(e["usage"]["input"] for e in composed)
        sources, processed = {}, {}
        for e in composed:
            item = compositions[(e["session"], e["request_id"])]
            for key, value in item["sources"].items():
                totals = sources.setdefault(key, {"new": 0, "carried": 0})
                totals["new"] += value["new"]
                totals["carried"] += value["carried"]
            for key, value in item.get("processed", {}).items():
                totals = processed.setdefault(key, {"results": 0, "new": 0, "carried": 0})
                for field in totals:
                    totals[field] += value[field]
        for totals in sources.values():
            totals["input_share_percent"] = percent(totals["new"] + totals["carried"], composed_input)
        # User messages and attachments by type, together: the single user_attachments source of earlier events.
        user = {"new": 0, "carried": 0}
        for key, totals in sources.items():
            if key in ("user_attachments", "user_message") or key.startswith("attachment:"):
                user["new"] += totals["new"]
                user["carried"] += totals["carried"]
        user["input_share_percent"] = percent(user["new"] + user["carried"], composed_input)
        composition = {"requests": len(composed), "input_tokens": composed_input,
                       "carried_tokens": sum(v["carried"] for v in sources.values()),
                       "sources": dict(sorted(sources.items(), key=lambda kv: -(kv[1]["new"] + kv[1]["carried"]))),
                       "user_attachments_total": user, "processed": processed,
                       "meaning": "calibrated estimates; carried = content repeated from earlier requests (cache reads); "
                                  "user_attachments_total = user_message plus every attachment:<type>"}
        fixed, pages = overhead_and_pages(uses, events, attribution_method, top)
        # What costs most, by three overlapping views: KB pages and listings are parts of the composition sources.
        costliest = {"sources": ranking({k: v["new"] + v["carried"] for k, v in sources.items()}, composed_input, top),
                     "kb_pages": ranking({k: v["new"] + v["carried"] for k, v in pages.pop("all").items()},
                                         pages["input_tokens"], top),
                     "fixed_overhead": ranking({v["name"]: v["replayed_tokens"] for v in fixed["items"]},
                                               fixed["input_tokens"], top)}
        return {"schema": SCHEMA, "session": session, "project": project_path(project) if project else None,
                "period": {"since": since, "until": until}, "events": len(events),
                "projects": projects(uses, costs, top),
                "context_composition": composition, "fixed_overhead": fixed, "kb_pages": pages,
                "cache_breaks": cache_breaks(uses, top, prices), "costliest": costliest,
                "lifecycle": lifecycle([e for e in events if e["kind"] == "lifecycle"]),
                "subagents": subagents(uses, costs),
                "coverage": coverage([e for e in events if e["kind"] == "coverage"], uses, snapshots, kb_root, top),
                "extension_metrics": extension_metrics([e for e in events if e["kind"] == "metric"]),
                "payload": {"deliveries": len(deliveries), "raw_tokens": raw, "presented_tokens": presented,
                            "saved_tokens": raw - presented, "saved_percent": percent(raw - presented, raw),
                            "count_methods": sorted({e["count_method"] for e in deliveries}),
                            "meaning": "tool payloads; not cumulative provider consumption"},
                "provider_usage": {"requests": len(uses), "input_tokens": sum(e["usage"]["input"] for e in uses),
                                   "cached_input_tokens": sum(e["usage"]["cached_input"] for e in uses),
                                   "cache_write_tokens": sum(e["usage"]["cache_write"] for e in uses),
                                   "cache_write_1h_tokens": sum(write_1h(e) for e in uses),
                                   "output_tokens": sum(e["usage"]["output"] for e in uses),
                                   "requests_output_lower_bound": sum(e.get("output_final") is False for e in uses),
                                   "requests_with_unpriced_server_tools": sum(any(e.get("server_tool_use", {}).values()) for e in uses),
                                   "requests_assuming_default_tier": sum(any(not (e.get("tier") or {}).get(k) for k in TIER) for e in uses),
                                   "clients": dict(sorted(Counter(client_label(e) for e in uses).items()))},
                "mem_attribution": {"covered_requests": len(covered), "uncovered_requests": len(uses) - len(covered),
                                    "input_tokens_on_covered_requests": mem_input if covered else None,
                                    "input_share_percent_on_covered_requests": percent(mem_input, total_input) if covered else None,
                                    "relative_to_nonmem_input_percent": percent(mem_input, total_input - mem_input) if covered else None,
                                    "output_tokens_on_covered_requests": sum(e["mem"]["output"] for e in covered) if covered else None,
                                    "methods": dict(sorted(Counter((e.get("attribution") or {}).get("method", "inline")
                                                                   for e in covered).items())),
                                    "input_tokens_by_category": dict(sorted(categories.items())),
                                    "counterfactual_without_mem_cost": None},
                "inventory_by_session": latest, "extensions": extension_stats,
                "money": money, "price_cards": [{k: p.get(k) for k in ("provider", "model", "currency", "as_of", "until",
                                                                       "basis")} for p in prices or []],
                "unpriced_requests": len(uses) - sum(i["priced_requests"] for i in money.values()),
                "unpriced_by_reason": dict(sorted(unpriced.items())),
                "requests_undated_priced_with_latest_card": undated,
                "requests_priced_before_card_date": {"total": sum(backdated.values()),
                                                     "by_card": dict(sorted(backdated.items()))}}


def ranking(volumes, total, top):
    return [{"name": k, "tokens": v, "input_share_percent": percent(v, total)}
            for k, v in sorted(volumes.items(), key=lambda kv: -kv[1])[:top]]


def overhead_and_pages(uses, events, method, top):
    """Fixed per-request overhead (system prompt, tool definitions, listings) and KB pages, from breakdown events."""
    breakdowns = {(e["session"], e["request_id"]): e for e in events if e["kind"] == "breakdown"
                  and (method is None or e["method"] == method)}
    overheads = {e["id"]: e for e in events if e["kind"] == "overhead"}
    details = [(e, breakdowns[(e["session"], e["request_id"])]) for e in uses if (e["session"], e["request_id"]) in breakdowns]
    first = {}
    for _, detail in details:
        for key in detail.get("overhead", []):
            if overheads.get(key, {}).get("source") == "prompt_snapshot":
                first.setdefault(key, detail.get("prefix", 0))
    # Snapshot sizes are character estimates. Scale each to the prefix of the first request it served: later
    # prefixes also absorb the estimation error that accumulates over a session.
    scale = {}
    for key, prefix in first.items():
        estimate = sum(overheads[key]["items"].values())
        ratio = prefix / estimate if estimate else 0
        scale[key] = ratio if 0.5 <= ratio <= 5 else 1.0
    items, calls, pages, last_call = {}, Counter(), {}, {}
    for use, detail in details:
        calls.update(detail.get("tools_called", {}))
        at = when(use)
        for tool in detail.get("tools_called", {}) if at else ():
            last_call[tool] = max(last_call.get(tool, at), at)
        for key in detail.get("overhead", []):
            for name_, tokens in (overheads.get(key) or {}).get("items", {}).items():
                size = tokens * scale.get(key, 1.0)
                item = items.setdefault(name_, {"requests": 0, "replayed_tokens": 0.0, "largest_tokens": 0})
                item["requests"] += 1
                item["replayed_tokens"] += size
                item["largest_tokens"] = max(item["largest_tokens"], round(size))
        for page, value in detail.get("kb_pages", {}).items():
            total = pages.setdefault(page, {"new": 0, "carried": 0})
            total["new"] += value["new"]
            total["carried"] += value["carried"]
    total_input = sum(e["usage"]["input"] for e, _ in details)
    servers = {}
    for name_, item in items.items():
        item["replayed_tokens"] = round(item["replayed_tokens"])
        item["input_share_percent"] = percent(item["replayed_tokens"], total_input)
        if name_.startswith("tool:"):
            item["calls"] = calls.get(name_[5:], 0)
            if name_.startswith("tool:mcp__"):
                server = servers.setdefault("mcp:" + name_.split("__")[1], {"tools": 0, "replayed_tokens": 0, "calls": 0})
                server["tools"] += 1
                server["replayed_tokens"] += item["replayed_tokens"]
                server["calls"] += item["calls"]
    for server in servers.values():
        server["input_share_percent"] = percent(server["replayed_tokens"], total_input)
    ranked = sorted(items.items(), key=lambda kv: -kv[1]["replayed_tokens"])
    # Every tool seen, loaded or called: tools called but absent from snapshots were deferred or not recorded.
    tools = {name_: {"calls": count, "loaded_requests": 0, "definition_replayed_tokens": 0,
                     "definition_input_share_percent": None} for name_, count in calls.items()}
    for name_, item in ranked:
        if name_.startswith("tool:"):
            tools.setdefault(name_[5:], {"calls": 0}).update(
                loaded_requests=item["requests"], definition_replayed_tokens=item["replayed_tokens"],
                definition_input_share_percent=item["input_share_percent"])
    for name_, tool in tools.items():
        tool["calls_per_1000_requests"] = (round(tool["calls"] * 1000 / tool["loaded_requests"], 2)
                                           if tool.get("loaded_requests") else None)
        tool["last_called"] = last_call[name_].date().isoformat() if name_ in last_call else None
    prefixes = sorted(d.get("prefix", 0) for _, d in details)
    snapshots = [sum(o["items"].values()) for o in overheads.values() if o["source"] == "prompt_snapshot"]
    fixed = {"requests": len(details), "input_tokens": total_input,
             "unexplained_prefix_tokens": {"p10": prefixes[len(prefixes) // 10], "median": statistics.median(prefixes),
                                           "p90": prefixes[len(prefixes) * 9 // 10]} if prefixes else None,
             "snapshot_estimate_tokens": statistics.median(snapshots) if snapshots else None,
             "items": [{"name": k, **v} for k, v in ranked],
             "mcp_servers": [{"name": k, **v} for k, v in sorted(servers.items(), key=lambda kv: -kv[1]["replayed_tokens"])],
             "loaded_never_called": [k for k, v in ranked if k.startswith("tool:") and not v["calls"]],
             # Called, but at most once per RARELY requests carrying the definition: still worth offering to disable.
             "rarely_called": [k for k, v in ranked if k.startswith("tool:") and v["calls"]
                               and v["calls"] * RARELY <= v["requests"]],
             "tool_usage": [{"tool": k, **v} for k, v in sorted(
                 tools.items(), key=lambda kv: (-kv[1]["definition_replayed_tokens"], -kv[1]["calls"], kv[0]))],
             "meaning": "replayed = item size x requests carrying it, mostly paid as cache reads; rarely called = at most "
                        "one call per 1000 requests carrying the tool; system prompt and "
                        "tool sizes scaled to the unexplained prefix of the first request they served, listings "
                        "calibrated; ranked lists, largest first"}
    for value in pages.values():
        value["input_share_percent"] = percent(value["new"] + value["carried"], total_input)
    ranked_pages = sorted(pages.items(), key=lambda kv: -(kv[1]["new"] + kv[1]["carried"]))
    kb = {"requests": len(details), "input_tokens": total_input, "pages": len(pages),
          "new_tokens": sum(v["new"] for v in pages.values()), "carried_tokens": sum(v["carried"] for v in pages.values()),
          "top": [{"page": k, **v} for k, v in ranked_pages[:top]], "all": dict(ranked_pages),
          "meaning": "KB content by page, calibrated; <shell> and <search> are commands and searches inside a KB, "
                     "<instructions> a MEM pointer in an instruction file outside it"}
    return fixed, kb


def seconds_between(earlier, later):
    try:
        return (moment(later) - moment(earlier)).total_seconds()
    except (TypeError, ValueError):
        return None


def lifecycle(events):
    """Compactions and fresh starts (/clear), with the context size around each compaction."""
    compactions = [e for e in events if e["event"] == "compaction"]
    before = sorted(e["tokens_before"] for e in compactions if e.get("tokens_before") is not None)
    after = sorted(e["tokens_after"] for e in compactions if e.get("tokens_after") is not None)
    return {"compactions": len(compactions),
            "compactions_by_trigger": dict(Counter(e.get("trigger") or "unknown" for e in compactions)),
            "tokens_before_median": statistics.median(before) if before else None,
            "tokens_after_median": statistics.median(after) if after else None,
            "clears": sum(1 for e in events if e["event"] == "clear"),
            "sessions_with_compaction": len({e["session"] for e in compactions}),
            "meaning": "compaction: the client summarised the context (auto or manual); clear: a fresh session "
                       "started with /clear"}


def projects(uses, costs, top):
    """Requests by project (the session's starting folder): tokens, API-equivalent cost when priced, MEM share."""
    rows = {}
    for e in uses:
        item = rows.setdefault(e.get("project") or "(unknown)", {
            "sessions": set(), "requests": 0, "input_tokens": 0, "cached_input_tokens": 0, "cache_write_tokens": 0,
            "output_tokens": 0, "cost": {}, "unpriced_requests": 0, "mem_input": 0, "covered_input": 0})
        item["sessions"].add(e["session"])
        item["requests"] += 1
        for key, bucket in (("input_tokens", "input"), ("cached_input_tokens", "cached_input"),
                            ("cache_write_tokens", "cache_write"), ("output_tokens", "output")):
            item[key] += e["usage"][bucket]
        cost = costs.get((e["session"], e["request_id"]))
        if cost:
            item["cost"][cost[0]] = item["cost"].get(cost[0], Decimal(0)) + cost[1]
        else:
            item["unpriced_requests"] += 1
        if e.get("mem") is not None:
            item["mem_input"] += e["mem"]["input"]
            item["covered_input"] += e["usage"]["input"]
    ranked = sorted(rows.items(), key=lambda kv: (-sum(kv[1]["cost"].values(), Decimal(0)), -kv[1]["input_tokens"]))
    return {"projects": len(rows), "top": [
        {"project": k, **{f: v for f, v in item.items() if f not in ("mem_input", "covered_input")},
         "sessions": len(item["sessions"]), "cost": {c: str(a) for c, a in sorted(item["cost"].items())},
         "mem_input_share_percent": percent(item["mem_input"], item["covered_input"]) if item["covered_input"] else None}
        for k, item in ranked[:top]],
        "meaning": "a project is the folder a session started in; ranked by API-equivalent cost, then input; MEM share "
                   "on requests with attribution"}


def subagents(uses, costs):
    """Subagent (sidechain) runs by agent type: runs, requests, tokens and API-equivalent cost when priced."""
    types, total = {}, sum(e["usage"]["input"] for e in uses)
    for e in uses:
        client = e.get("client") or {}
        if not client.get("sidechain"):
            continue
        item = types.setdefault(client.get("agent_type") or "unknown", {
            "runs": set(), "requests": 0, "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
            "cost": {}, "unpriced_requests": 0})
        item["runs"].add((e["session"], client.get("agent")))
        item["requests"] += 1
        for key, bucket in (("input_tokens", "input"), ("cached_input_tokens", "cached_input"), ("output_tokens", "output")):
            item[key] += e["usage"][bucket]
        cost = costs.get((e["session"], e["request_id"]))
        if cost:
            item["cost"][cost[0]] = item["cost"].get(cost[0], Decimal(0)) + cost[1]
        else:
            item["unpriced_requests"] += 1
    rows = []
    for kind, item in sorted(types.items(), key=lambda kv: -kv[1]["input_tokens"]):
        rows.append({"agent_type": kind, **item, "runs": len(item["runs"]),
                     "input_share_percent": percent(item["input_tokens"], total),
                     "cost": {k: str(v) for k, v in sorted(item["cost"].items())}})
    return {"runs": sum(r["runs"] for r in rows), "requests": sum(r["requests"] for r in rows),
            "input_tokens": sum(r["input_tokens"] for r in rows), "output_tokens": sum(r["output_tokens"] for r in rows),
            "input_share_percent": percent(sum(r["input_tokens"] for r in rows), total), "by_type": rows,
            "meaning": "requests made by subagents (sidechains); a run is one subagent instance; cost is "
                       "API-equivalent, only for priced requests"}


def coverage(events, uses, snapshots, kb_root, top):
    """What the adapters could not measure, as they recorded it, and how fresh each session's inventory is."""
    clients = {}
    for e in events:
        item = clients.setdefault(e["client"], {"sessions": 0, "counts": Counter(), "untested_versions": Counter()})
        item["sessions"] += 1
        item["counts"].update(e["counts"])
        item["untested_versions"].update(e.get("untested_versions", {}))
    used, recorded = {e["session"] for e in uses}, {e["session"] for e in events}
    now = datetime.now(timezone.utc)
    current = registry(kb_root) if kb_root else None
    latest = {}
    for e in snapshots:
        if when(e):
            latest[e["session"]] = e
    states = []
    for session, e in latest.items():
        at, snapshot = when(e), e["snapshot"]
        changed = None
        if current:
            if snapshot.get("registry_sha256"):
                changed = snapshot["registry_sha256"] != current[0]
            elif current[1]:
                changed = current[1] > at
        states.append({"session": session, "at": e["at"], "age_hours": round((now - at).total_seconds() / 3600, 1),
                       "registry_changed": changed})
    states.sort(key=lambda s: (s["registry_changed"] is not True, -s["age_hours"]))
    return {"by_client": {k: {"sessions": v["sessions"], **dict(sorted(v["counts"].items())),
                              "untested_versions": dict(sorted(v["untested_versions"].items()))}
                          for k, v in sorted(clients.items())},
            "sessions_with_usage_without_coverage": len(used - recorded),
            "inventory": {"snapshots": len(latest), "sessions_with_usage_without_inventory": len(used - set(latest)),
                          "registry_checked": current is not None,
                          "stale_sessions": sum(s["registry_changed"] is True for s in states), "sessions": states[:top]},
            "meaning": "counts the adapters recorded per session (pending, interrupted, inconsistent, skipped, "
                       "conflicts...); registry_changed: EXT.md or MEM.config.md changed after the session's latest "
                       "inventory snapshot (needs --kb-root)"}


def extension_metrics(events):
    """Extension-reported numbers by name and unit: count, sum, min, max."""
    metrics = {}
    for e in events:
        item = metrics.setdefault((e["name"], e.get("unit")), {"extension": e["extension"], "versions": set(), "count": 0,
                                                              "sum": 0, "min": None, "max": None, "latest_at": None})
        item["versions"].add(e["version"])
        item["count"] += 1
        item["sum"] += e["value"]
        item["min"] = e["value"] if item["min"] is None else min(item["min"], e["value"])
        item["max"] = e["value"] if item["max"] is None else max(item["max"], e["value"])
        if when(e) and (item["latest_at"] is None or when(e) > moment(item["latest_at"])):
            item["latest_at"] = e["at"]
    return {"metrics": [{"name": k[0], "unit": k[1], **v, "versions": sorted(v["versions"])}
                        for k, v in sorted(metrics.items(), key=lambda kv: (kv[0][0], kv[0][1] or ""))],
            "meaning": "numbers reported by extensions as metric events, aggregated per name and unit"}


def cache_breaks(uses, top, prices=None):
    """Later requests in a stream (a session or one subagent) that rewrote most of a large prompt into the cache."""
    streams = {}
    for e in uses:
        if when(e):
            streams.setdefault((e["session"], (e.get("client") or {}).get("agent")), []).append(e)
    causes, largest = {}, []
    for stream in streams.values():
        stream.sort(key=when)
        for previous, current in zip(stream, stream[1:]):
            counts = current["usage"]
            # Anthropic reports cache writes; OpenAI reports none, so input not read from the cache is what was
            # rewritten there.
            rewritten = max(counts["cache_write"], counts["input"] - counts["cached_input"])
            if counts["input"] < BREAK_MIN or rewritten < BREAK_SHARE * counts["input"]:
                continue
            idle = seconds_between(previous["at"], current["at"])
            if counts["input"] < BREAK_SHARE * previous["usage"]["input"]:
                cause = "context_reduced"  # compaction or similar: a much smaller prompt, written anew
            elif current["model"] != previous["model"]:
                cause = "model_changed"
            elif idle is not None and idle >= 3600:
                cause = "idle_over_1h"
            elif idle is not None and idle >= 1800 and current.get("provider") == "openai":
                cause = "idle_over_30m"  # OpenAI's prompt cache lifetime for GPT-5.6 and later
            elif idle is not None and idle >= 300 and write_1h(current) < counts["cache_write"]:
                cause = "idle_over_5m"
            else:
                cause = "other"
            item = causes.setdefault(cause, {"breaks": 0, "cache_write_tokens": 0, "write_cost": {}})
            item["breaks"] += 1
            item["cache_write_tokens"] += rewritten
            # What the rewrite cost, against reading the same tokens from the cache: an upper bound on the saving.
            card = card_for(prices, current)[0]
            written = {"input": counts["cache_write"], "cached_input": 0, "cache_write": counts["cache_write"], "output": 0}
            as_read = {"input": counts["cache_write"], "cached_input": counts["cache_write"], "cache_write": 0, "output": 0}
            cost = price(written, card, write_1h(current, written)) if card else None
            if cost is not None:
                money = item["write_cost"].setdefault(card["currency"], {"requests": 0, "written": Decimal(0),
                                                                         "if_read_from_cache": Decimal(0)})
                money["requests"] += 1
                money["written"] += cost
                money["if_read_from_cache"] += price(as_read, card)
            largest.append({"session": current["session"], "at": current["at"], "cause": cause,
                            "input_tokens": counts["input"], "cache_write_tokens": rewritten,
                            "idle_seconds": idle})
    largest.sort(key=lambda b: -b["cache_write_tokens"])
    for item in causes.values():
        for money in item["write_cost"].values():
            money["written"], money["if_read_from_cache"] = str(money["written"]), str(money["if_read_from_cache"])
    return {"breaks": sum(c["breaks"] for c in causes.values()),
            "cache_write_tokens": sum(c["cache_write_tokens"] for c in causes.values()),
            "all_cache_write_tokens": sum(e["usage"]["cache_write"] for e in uses),
            "by_cause": [{"cause": k, **v} for k, v in sorted(causes.items(), key=lambda kv: -kv[1]["cache_write_tokens"])],
            "largest": largest[:top],
            "meaning": "a later request in a stream writing at least half of a prompt of 10k+ tokens; idle time runs "
                       "between the ends of consecutive responses; context_reduced counts compactions among others"}


def percent(numerator, denominator):
    return float(numerator / denominator * 100) if denominator else None


def matches(card, event):
    tier = event.get("tier") or {}
    return card["provider"] == event["provider"] and card["model"] == event["model"] and all(
        (card.get(key) or default) == (tier.get(key) or default) for key, default in TIER.items())


def card_for(cards, event):
    """(card, reason): the matching card in force when the request was made - the latest as_of at or before its time,
    and before the card's until, if any. A card's as_of is when it was copied or verified, and per-model prices rarely
    change: a request older than every matching card takes the earliest one, back-dated and counted (reason
    before_card_date). Other reasons: dated, undated (no request time: the latest card applies), no_matching_card,
    after_card_until (past the until of the card in force: unpriced)."""
    matching = [c for c in cards or [] if matches(c, event)]
    if not matching:
        return None, "no_matching_card"
    at = when(event)
    if at is None:
        return max(matching, key=lambda c: moment(c["as_of"])), "undated"
    valid = [c for c in matching if moment(c["as_of"]) <= at and (not c.get("until") or at < moment(c["until"]))]
    if valid:
        return max(valid, key=lambda c: moment(c["as_of"])), "dated"
    if all(at < moment(c["as_of"]) for c in matching):
        return min(matching, key=lambda c: moment(c["as_of"])), "before_card_date"
    return None, "after_card_until"


def card_label(card):
    """provider/model[/tier values]@as_of: names a price card in reports."""
    tiers = [str(card[k]) for k in TIER if card.get(k) and card[k] != TIER[k]]
    return "/".join([card["provider"], card["model"]] + tiers) + "@" + str(card["as_of"])


def write_1h(event, counts=None):
    """1h cache-write tokens in counts (default: the whole request); None when a share cannot be known."""
    long = (event.get("usage_detail") or {}).get("cache_write_1h", 0)
    if counts is None or long == 0 or counts["cache_write"] == 0:
        return long if counts is None else 0
    # A MEM/extension share of mixed 5m and 1h writes is not recorded; refuse to guess its price.
    return counts["cache_write"] if long == event["usage"]["cache_write"] else None


def client_label(event):
    client = event.get("client") or {}
    return (client.get("name") or "unspecified") + ("/" + client["version"] if client.get("version") else "")


def price(counts, card, long_writes=0):
    """Cost per million rates; long_writes are priced at cache_write_1h. None when not priceable."""
    if long_writes is None or (long_writes and card.get("cache_write_1h") is None):
        return None
    rates = [Decimal(str(card[key])) for key in ("input", "cached_input", "cache_write", "output")]
    long_rate = Decimal(str(card["cache_write_1h"])) if long_writes else rates[2]
    if not card.get("currency") or not card.get("as_of") or any(not r.is_finite() or r < 0 for r in rates + [long_rate]):
        raise ValueError("prices require currency, as_of and finite non-negative rates per million")
    amount = sum((Decimal(n) * r for n, r in zip(portions(counts), rates)), Decimal(0))
    return (amount + Decimal(long_writes) * (long_rate - rates[2])) / Decimal(1_000_000)


def select(report, sections):
    """The report limited to these sections (the header fields always stay)."""
    if not sections:
        return report
    keep = {"schema", "session", "project", "period", "events"} | set(sections)
    if "money" in sections:
        keep |= {"price_cards", "unpriced_requests", "unpriced_by_reason", "requests_undated_priced_with_latest_card",
                 "requests_priced_before_card_date"}
    return {k: v for k, v in report.items() if k in keep}


MONEY_KEYS = {"total", "mem_allocated", "covered_total", "amount", "written", "if_read_from_cache"}
CURRENCIES = {"USD", "EUR", "GBP"}


def number(value, key="", nested=False):
    """A value as text: thousands separators, percentages, money with two decimals (more below one unit)."""
    if value is None or value in ({}, []):
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str) and (key in MONEY_KEYS or key in CURRENCIES):
        try:
            amount = Decimal(value)
            return f"{amount:,.2f}" if abs(amount) >= 1 or amount == 0 else f"{amount:.6f}".rstrip("0")
        except ArithmeticError:
            pass
    if isinstance(value, float):
        if "percent" in key:
            return f"{value:.1f}%"
        return f"{value:,.0f}" if value.is_integer() or abs(value) >= 100 else f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, (dict, list)):
        if nested and not flat(value):
            # One level more fits a cell when small, e.g. money by currency; otherwise only a count.
            if isinstance(value, dict) and len(value) <= 3 and all(
                    isinstance(v, dict) and flat(v) and len(v) <= 4 for v in value.values()):
                return "; ".join(str(k) + ": " + number(v, str(k), True) for k, v in value.items())
            return "(" + str(len(value)) + " entries)"
        if isinstance(value, dict):
            return ", ".join(str(k).replace("_", " ") + " " + number(v, str(k), True) for k, v in value.items())
        return ", ".join(number(v, key, True) for v in value)
    return str(value).replace("|", "\\|")


def flat(value):
    items = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    return all(not isinstance(v, (dict, list)) for v in items)


def table(rows):
    """Markdown table of a list of dicts, columns in first-seen order."""
    if not rows:
        return ["(none)"]
    columns = []
    for row in rows:
        for key in row:
            if key not in columns and key != "meaning":
                columns.append(key)
    lines = ["| " + " | ".join(c.replace("_", " ") for c in columns) + " |", "|" + "---|" * len(columns)]
    for row in rows:
        lines.append("| " + " | ".join(number(row.get(c), c, True) for c in columns) + " |")
    return lines


def block(value, depth=3):
    """Markdown for one report value: scalars in a field/value table, records (lists, or maps keyed by name) as
    tables, anything else under its own heading."""
    if isinstance(value, list):
        return table(value) if value and all(isinstance(v, dict) for v in value) else [number(value)]
    if not isinstance(value, dict):
        return [number(value)]
    if value and all(isinstance(v, dict) and flat(v) for v in value.values()):
        return table([{"name": k, **v} for k, v in value.items()])
    lines, scalars, nested = [], {}, []
    for key, item in value.items():
        if key == "meaning":
            continue
        if isinstance(item, dict) and item and all(isinstance(v, dict) and flat(v) for v in item.values()):
            nested.append((key, table([{"name": k, **v} for k, v in item.items()])))
        elif isinstance(item, list) and item and all(isinstance(v, dict) for v in item):
            nested.append((key, table(item)))
        elif isinstance(item, dict) and (len(item) > 6 or not flat(item)):
            nested.append((key, block(item, depth + 1)))
        else:
            scalars[key] = item
    if scalars:
        lines += ["| field | value |", "|---|---|"] + ["| " + k.replace("_", " ") + " | " + number(v, k) + " |"
                                                       for k, v in scalars.items()]
    for key, body in nested:
        lines += ["", "#" * min(depth, 6) + " " + key.replace("_", " "), ""] + body
    if value.get("meaning"):
        lines += ["", "_" + value["meaning"] + "_"]
    return lines[1:] if lines and not lines[0] else lines


def render_text(report, sections=None):
    """The report as readable Markdown: one heading per section, compact tables, formatted numbers. Without a
    selection every section but inventory_by_session (one table per session) is shown."""
    period = report.get("period") or {}
    lines = ["# mem-stats report", "",
             "session: " + (report.get("session") or "all") + " · project: " + (report.get("project") or "all")
             + " · period: " + (period.get("since") or "start") + " to "
             + (period.get("until") or "now") + " · events: " + number(report.get("events"))]
    for key in SECTIONS:
        if key not in report or (key not in sections if sections else key == "inventory_by_session"):
            continue
        lines += ["", "## " + key.replace("_", " ").capitalize(), ""] + block(report[key])
        if key == "money":
            lines += ["", "| field | value |", "|---|---|"] + [
                "| " + k.replace("_", " ") + " | " + number(report.get(k), k) + " |"
                for k in ("unpriced_requests", "unpriced_by_reason", "requests_undated_priced_with_latest_card",
                          "requests_priced_before_card_date")
                if k in report]
            if report.get("price_cards"):
                lines += ["", "### price cards", ""] + table(report["price_cards"])
    return "\n".join(lines) + "\n"


def make_event(session, kind, **values):
    return {"schema": SCHEMA, "id": str(uuid.uuid4()), "session": session, "kind": kind,
            "at": datetime.now(timezone.utc).isoformat(), **values}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("ingest", help="ingest JSONL events from stdin; rejected lines are reported on stderr by line "
                                       "number and the exit code is 1 if any; no success messages")
    for name_ in ("report", "watch"):
        cmd = commands.add_parser(name_)
        cmd.add_argument("--session")
        cmd.add_argument("--prices", type=Path)
        cmd.add_argument("--attribution-method", help="use only this attribution method (default: latest per request)")
        cmd.add_argument("--since", help="only requests at or after this ISO date/time, e.g. 2026-10-15 (UTC if no zone)")
        cmd.add_argument("--until", help="only requests before this ISO date/time")
        cmd.add_argument("--top", type=int, default=10, help="entries in ranked lists (default 10)")
        cmd.add_argument("--format", choices=("json", "text"), default="json",
                         help="json (default) or text: Markdown with one heading per section")
        cmd.add_argument("--sections", help="comma-separated sections to include (default: all; text omits "
                                            "inventory_by_session unless named): " + ",".join(SECTIONS))
        cmd.add_argument("--kb-root", type=Path, help="KB root whose EXT.md and MEM.config.md are compared with each "
                                                      "session's latest inventory snapshot")
        cmd.add_argument("--project", help="only sessions started in this folder or under it")
        if name_ == "watch":
            cmd.add_argument("--interval", type=float, default=2)
    prune = commands.add_parser("prune", help="delete whole sessions last active before a date")
    prune.add_argument("--before", required=True, help="ISO date/time, e.g. 2026-07-01 (UTC if no zone)")
    inv = commands.add_parser("inventory")
    inv.add_argument("--kb-root", type=Path, required=True)
    inv.add_argument("--manifest", type=Path)
    inv.add_argument("--session", required=True)
    read = commands.add_parser("read", help="instrumented full read; content only on stdout")
    read.add_argument("--kb-root", type=Path, required=True)
    read.add_argument("--session", required=True)
    read.add_argument("--encoding")
    read.add_argument("path")
    args = parser.parse_args()
    collector = Collector(args.db, create=args.command == "init", batch=BATCH if args.command == "ingest" else 0)
    try:
        def emit(content):
            sys.stdout.write(content)
            sys.stdout.flush()
        if args.command == "ingest":
            rejected = 0
            for number_, line in enumerate(sys.stdin, 1):
                if not line.strip():
                    continue
                try:
                    outcome = collector.offer(json.loads(line))
                except (ValueError, KeyError, TypeError, AttributeError) as error:
                    outcome = "rejected: " + (str(error)[:200] if isinstance(error, ValueError) else
                                              type(error).__name__ + " " + str(error)[:60])
                if outcome == "conflict":
                    outcome = "conflict: measured counts differ from the stored event; skipped"
                elif outcome == "skipped":
                    outcome = "skipped: estimate of a request whose usage conflicted"
                if outcome not in ("inserted", "replaced", "unchanged", "kept"):
                    rejected += 1
                    print("line " + str(number_) + ": " + outcome, file=sys.stderr)
            if rejected:
                print(json.dumps({"rejected": rejected, **dict(sorted(collector.outcomes.items()))}, sort_keys=True),
                      file=sys.stderr)
                return 1
        elif args.command == "prune":
            emit(json.dumps(collector.prune(args.before), sort_keys=True) + "\n")
        elif args.command == "inventory":
            snapshot = inventory(args.kb_root, args.manifest)
            collector.add(make_event(args.session, "inventory", snapshot=snapshot))
            emit(json.dumps(snapshot, indent=2) + "\n")
        elif args.command == "read":
            path = checked_path(args.kb_root, args.path)
            content = path.read_bytes().decode("utf-8-sig")
            count, method = token_count(content, args.encoding)
            relative = path.relative_to(args.kb_root.resolve()).as_posix()
            origin = relative.split("/")[1] if relative.startswith("extensions/") and "/" in relative[11:] else "mem-core"
            collector.add(make_event(args.session, "delivery", source_extension=origin, processor_extension=None,
                                    path=relative, raw_tokens=count, presented_tokens=count, count_method=method))
            emit(content)
        elif args.command in ("report", "watch"):
            prices = json.loads(args.prices.read_text(encoding="utf-8-sig")) if args.prices else None
            if args.command == "watch" and args.interval <= 0:
                raise ValueError("interval must be positive")
            sections = [s.strip() for s in args.sections.split(",") if s.strip()] if args.sections else None
            if sections and set(sections) - set(SECTIONS):
                raise ValueError("unknown sections: " + ", ".join(sorted(set(sections) - set(SECTIONS))))
            moment(args.since), moment(args.until)
            where = " WHERE session=?" if args.session else ""
            query = ("SELECT count(*), max(rowid), (SELECT payload FROM events" + where + " ORDER BY rowid DESC "
                     "LIMIT 1) FROM events" + where)
            previous, version, signature = None, None, None
            while True:
                # The report is never stored, so it cannot trigger itself. Rebuild only when the ledger changed:
                # data_version moves on commits by other connections, and a replaced event takes a new rowid - except
                # the last one, whose rowid SQLite reuses, hence the last payload in the signature.
                current = collector.db.execute("PRAGMA data_version").fetchone()[0]
                if current != version:
                    version = current
                    signature = collector.db.execute(query, (args.session,) * 2 if args.session else ()).fetchone()
                if signature != previous:
                    report = select(collector.report(args.session, prices, args.attribution_method, args.since,
                                                     args.until, args.top, args.kb_root, args.project), sections)
                    if args.format == "text":
                        emit(render_text(report, sections) + ("\n" if args.command == "watch" else ""))
                    else:
                        emit(json.dumps(report, sort_keys=True) + "\n")
                    previous = signature
                if args.command != "watch":
                    break
                time.sleep(args.interval)
    finally:
        collector.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", newline="")
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, ImportError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
