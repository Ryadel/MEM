"""Local event collector. No model calls, hooks, network traffic or mem-optimize dependency."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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

VERSION = "0.1.0"
SCHEMA = "mem-stats/1"
LIFECYCLE = ("compaction", "clear")
BUCKETS = ("input", "cached_input", "cache_write", "output")
# Pricing tier attributes and the value assumed when an event or price card omits one.
TIER = {"service_tier": "standard", "speed": "standard", "inference_geo": "global"}
# A later request writing at least this share of a prompt at least this large rewrote the cache: a cache break.
BREAK_SHARE, BREAK_MIN = 0.5, 10_000


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
        index = ext / key / "index.md"
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
            "extensions": result}


class Collector:
    def __init__(self, path, create=False):
        self.path = Path(path).resolve()
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        elif not self.path.is_file():
            raise ValueError("stats is not initialized")
        self.db = sqlite3.connect(str(self.path), timeout=15)
        self.db.execute("PRAGMA busy_timeout=15000")
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

    def close(self):
        self.db.close()

    def prune(self, before):
        """Delete whole sessions whose latest timed event is before `before`; never half a session. Overhead events
        still referenced by a kept breakdown stay. Sessions without any timed event have no known age and stay."""
        rows = self.db.execute("SELECT id, session, kind, payload FROM events").fetchall()
        latest, untimed = {}, set()
        for _, session, _, payload in rows:
            at = json.loads(payload).get("at")
            if at:
                latest[session] = max(latest.get(session, ""), at)
            else:
                untimed.add(session)
        old = {s for s, at in latest.items() if at < before}
        referenced = {key for _, session, kind, payload in rows if kind == "breakdown" and session not in old
                      for key in json.loads(payload).get("overhead", [])}
        doomed = [(i,) for i, session, kind, _ in rows if session in old and not (kind == "overhead" and i in referenced)]
        with self.db:
            self.db.executemany("DELETE FROM events WHERE id=?", doomed)
        self.db.execute("VACUUM")
        return {"before": before, "sessions_deleted": len(old), "events_deleted": len(doomed),
                "sessions_without_age": len(untimed - set(latest))}

    def add(self, event):
        if not isinstance(event, dict) or event.get("schema") != SCHEMA:
            raise ValueError("event schema must be " + SCHEMA)
        for key in ("id", "session", "kind"):
            if not isinstance(event.get(key), str) or not event[key].strip():
                raise ValueError("event requires " + key)
        kind = event["kind"]
        if kind == "delivery":
            for key in ("raw_tokens", "presented_tokens"):
                integer(event[key])
            if not event.get("count_method"):
                raise ValueError("delivery requires count_method")
            if not isinstance(event.get("source_extension"), str):
                raise ValueError("delivery requires source_extension")
        elif kind == "usage":
            total = buckets(event["usage"])
            if not all(isinstance(event.get(k), str) and event[k] for k in ("provider", "model", "request_id")):
                raise ValueError("usage requires provider, model and request_id")
            if event["id"] != "usage:" + event["session"] + ":" + event["request_id"]:
                raise ValueError("usage id must be usage:<session>:<request_id>")
            mem = buckets(event["mem"]) if event.get("mem") is not None else None
            if mem:
                subset(mem, total)
            allocated = [buckets(v) for v in event.get("extensions", {}).values()]
            sums = {k: sum(v[k] for v in allocated) for k in BUCKETS}
            subset(sums, mem if mem is not None else total)
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
            tools = event.get("server_tool_use", {})
            if not isinstance(tools, dict):
                raise ValueError("server_tool_use must map tool names to counts")
            for count in tools.values():
                integer(count)
            if "output_final" in event and type(event["output_final"]) is not bool:
                raise ValueError("output_final must be a boolean")
        elif kind == "attribution":
            # An estimate kept apart from measured usage, so a better method can be added without conflicts.
            if not all(isinstance(event.get(k), str) and event[k] for k in ("request_id", "method", "count_method")):
                raise ValueError("attribution requires request_id, method and count_method")
            if event["id"] != "attribution:" + event["session"] + ":" + event["request_id"] + ":" + event["method"]:
                raise ValueError("attribution id must be attribution:<session>:<request_id>:<method>")
            row = self.db.execute("SELECT payload FROM events WHERE id=?",
                                  ("usage:" + event["session"] + ":" + event["request_id"],)).fetchone()
            if row is None:
                raise ValueError("attribution requires its usage event")
            mem = buckets(event["mem"])
            subset(mem, json.loads(row[0])["usage"])
            allocated = [buckets(v) for v in event.get("extensions", {}).values()]
            subset({k: sum(v[k] for v in allocated) for k in BUCKETS}, mem)
            categories = event.get("categories", {})
            if not isinstance(categories, dict) or sum(integer(v) for v in categories.values()) > mem["input"]:
                raise ValueError("attribution categories must be input counts within mem input")
        elif kind == "composition":
            if not all(isinstance(event.get(k), str) and event[k] for k in ("request_id", "method")):
                raise ValueError("composition requires request_id and method")
            if event["id"] != "composition:" + event["session"] + ":" + event["request_id"] + ":" + event["method"]:
                raise ValueError("composition id must be composition:<session>:<request_id>:<method>")
            row = self.db.execute("SELECT payload FROM events WHERE id=?",
                                  ("usage:" + event["session"] + ":" + event["request_id"],)).fetchone()
            if row is None:
                raise ValueError("composition requires its usage event")
            sources, processed = event.get("sources"), event.get("processed", {})
            if not isinstance(sources, dict) or not isinstance(processed, dict) or any(
                    not isinstance(v, dict) or set(v) != {"new", "carried"} for v in sources.values()) or any(
                    not isinstance(v, dict) or set(v) != {"results", "new", "carried"} for v in processed.values()):
                raise ValueError("composition sources need new/carried counts; processed adds results")
            content = sum(integer(v["new"]) + integer(v["carried"]) for v in sources.values())
            for v in processed.values():
                integer(v["results"]), integer(v["new"]), integer(v["carried"])
            if content > json.loads(row[0])["usage"]["input"]:
                raise ValueError("composition exceeds the request's input")
        elif kind == "breakdown":
            if not all(isinstance(event.get(k), str) and event[k] for k in ("request_id", "method")):
                raise ValueError("breakdown requires request_id and method")
            if event["id"] != "breakdown:" + event["session"] + ":" + event["request_id"] + ":" + event["method"]:
                raise ValueError("breakdown id must be breakdown:<session>:<request_id>:<method>")
            row = self.db.execute("SELECT payload FROM events WHERE id=?",
                                  ("usage:" + event["session"] + ":" + event["request_id"],)).fetchone()
            if row is None:
                raise ValueError("breakdown requires its usage event")
            pages, calls, overhead = event.get("kb_pages", {}), event.get("tools_called", {}), event.get("overhead", [])
            if not isinstance(pages, dict) or any(not isinstance(v, dict) or set(v) != {"new", "carried"}
                                                  for v in pages.values()) or not isinstance(calls, dict) or not \
                    isinstance(overhead, list) or any(not isinstance(i, str) for i in overhead):
                raise ValueError("breakdown needs kb_pages new/carried counts, tools_called counts and overhead ids")
            for count in calls.values():
                integer(count)
            limit = json.loads(row[0])["usage"]["input"]
            if integer(event.get("prefix", 0)) > limit or sum(
                    integer(v["new"]) + integer(v["carried"]) for v in pages.values()) > limit:
                raise ValueError("breakdown exceeds the request's input")
        elif kind == "overhead":
            items = event.get("items")
            if not isinstance(event.get("source"), str) or not event["source"] or not isinstance(items, dict) or not items:
                raise ValueError("overhead requires a source and token counts by item")
            for count in items.values():
                integer(count)
        elif kind == "inventory":
            if not isinstance(event.get("snapshot", {}).get("extensions"), list):
                raise ValueError("inventory requires an extension snapshot")
        elif kind == "lifecycle":
            if event.get("event") not in LIFECYCLE or not isinstance(event.get("at"), str) or not event["at"]:
                raise ValueError("lifecycle requires event (" + ", ".join(LIFECYCLE) + ") and at")
            for key in ("tokens_before", "tokens_after", "duration_ms"):
                if event.get(key) is not None:
                    integer(event[key])
        else:
            raise ValueError("unsupported event kind")
        payload = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        with self.db:
            inserted = self.db.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?)", (event["id"], event["session"], kind, payload)).rowcount
            previous = self.db.execute("SELECT payload FROM events WHERE id=?", (event["id"],)).fetchone()
            if previous[0] != payload:
                raise ValueError("conflicting duplicate event id")
        return bool(inserted)

    def report(self, session=None, prices=None, attribution_method=None, since=None, until=None, top=10):
        rows = self.db.execute("SELECT payload FROM events" + (" WHERE session=?" if session else "") + " ORDER BY rowid",
                               (session,) if session else ()).fetchall()
        events = [json.loads(row[0]) for row in rows]
        if since or until:
            # A period keeps timed events within [since, until); estimates follow the usage they belong to.
            def within(e):
                at = e.get("at") or ""
                return bool(at) and (not since or at >= since) and (not until or at < until)
            kept = {(e["session"], e["request_id"]) for e in events if e["kind"] == "usage" and within(e)}
            events = [e for e in events if (e["session"], e.get("request_id")) in kept
                      if e["kind"] in ("usage", "attribution", "composition", "breakdown")] + [
                e for e in events if e["kind"] in ("delivery", "lifecycle") and within(e)] + [
                e for e in events if e["kind"] in ("inventory", "overhead")]
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
        money = {}
        for event in uses:
            card = next((p for p in prices or [] if matches(p, event)), None)
            if card is None:
                continue
            total_cost = price(event["usage"], card, write_1h(event))
            if total_cost is None:
                continue  # 1h cache writes need a rate the card lacks: unpriced, not zero
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
                    costs = extension.setdefault("allocated_money", {})
                    values = costs.setdefault(card["currency"], {"requests": 0, "amount": Decimal(0)})
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
        composition = {"requests": len(composed), "input_tokens": composed_input,
                       "carried_tokens": sum(v["carried"] for v in sources.values()),
                       "sources": dict(sorted(sources.items(), key=lambda kv: -(kv[1]["new"] + kv[1]["carried"]))),
                       "processed": processed,
                       "meaning": "calibrated estimates; carried = content repeated from earlier requests (cache reads)"}
        fixed, pages = overhead_and_pages(uses, events, attribution_method, top)
        # What costs most, by three overlapping views: KB pages and listings are parts of the composition sources.
        costliest = {"sources": ranking({k: v["new"] + v["carried"] for k, v in sources.items()}, composed_input, top),
                     "kb_pages": ranking({k: v["new"] + v["carried"] for k, v in pages.pop("all").items()},
                                         pages["input_tokens"], top),
                     "fixed_overhead": ranking({v["name"]: v["replayed_tokens"] for v in fixed["items"]},
                                               fixed["input_tokens"], top)}
        return {"schema": SCHEMA, "session": session, "period": {"since": since, "until": until}, "events": len(events),
                "context_composition": composition, "fixed_overhead": fixed, "kb_pages": pages,
                "cache_breaks": cache_breaks(uses, top, prices), "costliest": costliest,
                "lifecycle": lifecycle([e for e in events if e["kind"] == "lifecycle"]),
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
                "money": money, "price_cards": [{k: p.get(k) for k in ("provider", "model", "currency", "as_of", "basis")}
                                                for p in prices or []],
                "unpriced_requests": len(uses) - sum(i["priced_requests"] for i in money.values())}


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
        for key in detail["overhead"]:
            if overheads.get(key, {}).get("source") == "prompt_snapshot":
                first.setdefault(key, detail["prefix"])
    # Snapshot sizes are character estimates. Scale each to the prefix of the first request it served: later
    # prefixes also absorb the estimation error that accumulates over a session.
    scale = {}
    for key, prefix in first.items():
        estimate = sum(overheads[key]["items"].values())
        ratio = prefix / estimate if estimate else 0
        scale[key] = ratio if 0.5 <= ratio <= 5 else 1.0
    items, calls, pages = {}, Counter(), {}
    for _, detail in details:
        calls.update(detail["tools_called"])
        for key in detail["overhead"]:
            for name, tokens in (overheads.get(key) or {}).get("items", {}).items():
                size = tokens * scale.get(key, 1.0)
                item = items.setdefault(name, {"requests": 0, "replayed_tokens": 0.0, "largest_tokens": 0})
                item["requests"] += 1
                item["replayed_tokens"] += size
                item["largest_tokens"] = max(item["largest_tokens"], round(size))
        for page, value in detail["kb_pages"].items():
            total = pages.setdefault(page, {"new": 0, "carried": 0})
            total["new"] += value["new"]
            total["carried"] += value["carried"]
    total_input = sum(e["usage"]["input"] for e, _ in details)
    servers = {}
    for name, item in items.items():
        item["replayed_tokens"] = round(item["replayed_tokens"])
        item["input_share_percent"] = percent(item["replayed_tokens"], total_input)
        if name.startswith("tool:"):
            item["calls"] = calls.get(name[5:], 0)
            if name.startswith("tool:mcp__"):
                server = servers.setdefault("mcp:" + name.split("__")[1], {"tools": 0, "replayed_tokens": 0, "calls": 0})
                server["tools"] += 1
                server["replayed_tokens"] += item["replayed_tokens"]
                server["calls"] += item["calls"]
    for server in servers.values():
        server["input_share_percent"] = percent(server["replayed_tokens"], total_input)
    ranked = sorted(items.items(), key=lambda kv: -kv[1]["replayed_tokens"])
    # Every tool seen, loaded or called: tools called but absent from snapshots were deferred or not recorded.
    tools = {name: {"calls": count, "loaded_requests": 0, "definition_replayed_tokens": 0,
                    "definition_input_share_percent": None} for name, count in calls.items()}
    for name, item in ranked:
        if name.startswith("tool:"):
            tools.setdefault(name[5:], {"calls": 0}).update(
                loaded_requests=item["requests"], definition_replayed_tokens=item["replayed_tokens"],
                definition_input_share_percent=item["input_share_percent"])
    prefixes = sorted(d["prefix"] for _, d in details)
    snapshots = [sum(o["items"].values()) for o in overheads.values() if o["source"] == "prompt_snapshot"]
    fixed = {"requests": len(details), "input_tokens": total_input,
             "unexplained_prefix_tokens": {"p10": prefixes[len(prefixes) // 10], "median": statistics.median(prefixes),
                                           "p90": prefixes[len(prefixes) * 9 // 10]} if prefixes else None,
             "snapshot_estimate_tokens": statistics.median(snapshots) if snapshots else None,
             "items": [{"name": k, **v} for k, v in ranked],
             "mcp_servers": [{"name": k, **v} for k, v in sorted(servers.items(), key=lambda kv: -kv[1]["replayed_tokens"])],
             "loaded_never_called": [k for k, v in ranked if k.startswith("tool:") and not v["calls"]],
             "tool_usage": [{"tool": k, **v} for k, v in sorted(
                 tools.items(), key=lambda kv: (-kv[1]["definition_replayed_tokens"], -kv[1]["calls"], kv[0]))],
             "meaning": "replayed = item size x requests carrying it, mostly paid as cache reads; system prompt and "
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
        return (datetime.fromisoformat(later) - datetime.fromisoformat(earlier)).total_seconds()
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


def cache_breaks(uses, top, prices=None):
    """Later requests in a stream (a session or one subagent) that rewrote most of a large prompt into the cache."""
    streams = {}
    for e in uses:
        if e.get("at"):
            streams.setdefault((e["session"], (e.get("client") or {}).get("agent")), []).append(e)
    causes, largest = {}, []
    for stream in streams.values():
        stream.sort(key=lambda e: e["at"])
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
            card = next((p for p in prices or [] if matches(p, current)), None)
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


def make_event(session, kind, **values):
    return {"schema": SCHEMA, "id": str(uuid.uuid4()), "session": session, "kind": kind,
            "at": datetime.now(timezone.utc).isoformat(), **values}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("ingest", help="ingest JSONL events from stdin; emits no success messages")
    for name in ("report", "watch"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--session")
        cmd.add_argument("--prices", type=Path)
        cmd.add_argument("--attribution-method", help="use only this attribution method (default: latest per request)")
        cmd.add_argument("--since", help="only requests at or after this ISO date/time, e.g. 2026-10-15")
        cmd.add_argument("--until", help="only requests before this ISO date/time")
        cmd.add_argument("--top", type=int, default=10, help="entries in ranked lists (default 10)")
        if name == "watch":
            cmd.add_argument("--interval", type=float, default=2)
    prune = commands.add_parser("prune", help="delete whole sessions last active before a date")
    prune.add_argument("--before", required=True, help="ISO date/time, e.g. 2026-07-01")
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
    collector = Collector(args.db, create=args.command == "init")
    try:
        def emit(content):
            sys.stdout.write(content)
            sys.stdout.flush()
        if args.command == "ingest":
            for line in sys.stdin:
                if line.strip():
                    collector.add(json.loads(line))
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
            previous = None
            while True:
                # A report records its own payload once, but must not trigger another report forever.
                query = "SELECT id,payload FROM events" + (" WHERE session=?" if args.session else "")
                signature = tuple(row[0] for row in collector.db.execute(query, (args.session,) if args.session else ())
                                  if json.loads(row[1]).get("purpose") != "report")
                if signature != previous or args.command == "report":
                    emit(json.dumps(collector.report(args.session, prices, args.attribution_method, args.since, args.until,
                                                     args.top),
                                    sort_keys=True) + "\n")
                    previous = signature
                if args.command != "watch":
                    break
                time.sleep(args.interval)
    finally:
        collector.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", newline="")
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, ImportError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
