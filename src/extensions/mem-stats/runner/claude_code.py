"""Claude Code usage adapter. Reads local transcripts; emits mem-stats/1 usage, attribution, composition,
breakdown, overhead, lifecycle and coverage events.

Read-only, no network. Attribution needs at least one KB root (a folder holding MEM.md and MEM.config.md).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import statistics
import sys
import time
from pathlib import Path

SCHEMA = "mem-stats/1"
CLIENT = "claude-code"
# Transcript layouts this parser was verified against; others are parsed if well-formed but reported.
TESTED_VERSIONS = ("2.1.",)
USAGE_KEYS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens")
# Bump when the estimate changes in kind: the ledger keeps the latest attribution per request and method, and a
# new method name keeps the old estimates for comparison.
METHOD = "claude-code-positional/1"
# Bump when the events derived for a settled request change: incremental runs recompute stored requests only when
# the revision (or the run's context: KB roots, attribution, composition, tokenizer) differs from the stored one.
REVISION = 2
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
PATH_KEYS = ("file_path", "notebook_path", "path")
COMMAND_TOOLS = {"Bash", "PowerShell"}
# An instruction file naming these is a MEM pointer, and counts as MEM in full.
POINTER_MARKERS = ("mem.index.md", "mem.config.md")
NAME_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789._-"
# Traces sqz leaves in output it compressed. Absent markers do not prove sqz left an output untouched.
SQZ_MARKERS = re.compile(r"\[Abbreviations\]|sqz expand [0-9a-f]{8,}|§ref:[0-9a-f]{8,}§|^\[sqz\]", re.M)
# Attachments Claude Code adds once and every later request carries: fixed overhead, like tool definitions.
LISTINGS = {"skill_listing", "agent_listing_delta", "deferred_tools_delta", "mcp_instructions_delta", "instructions"}
# Identifiers the ledger accepts (stats.NAME, 128 characters) and KB page labels (stats.LABEL, 300 characters).
NAME = re.compile(r"[\w.:@/+<>\[\]-]{1,100}")
LABEL = re.compile(r"[^\x00-\x1f\x7f]{1,300}")


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


def first_cwd(path, main=True):
    """The working folder of a transcript's first main-chain line (any line when main is False)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if '"cwd"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict) and isinstance(record.get("cwd"), str) and record["cwd"] and not (
                        main and record.get("isSidechain")):
                    return record["cwd"]
    except OSError:
        pass
    return None


def safe(name, fallback="other"):
    """A client-supplied name (tool, attachment type, agent type) as a ledger identifier, or the fallback."""
    return name if isinstance(name, str) and NAME.fullmatch(name) else fallback


def tool_label(name):
    if isinstance(name, str) and name.startswith("mcp__"):
        return "mcp:" + safe(name.split("__")[1])
    return safe(name, "unknown") if name else "unknown"


def projects_dir():
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / "projects"


def workspace_folder(workspace):
    """Claude Code names a project folder after its workspace path, every non-alphanumeric replaced by '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(workspace))


def transcripts(folder):
    """Main session transcripts and their subagent transcripts."""
    return sorted(folder.glob("*.jsonl")) + sorted(folder.glob("*/subagents/*.jsonl"))


SKIP_FOLDERS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tmp"}  # .tmp: MEM's agent_tmp_dir default; test KBs live there


def find_kb_roots(workspace, depth=4):
    """KB roots under a workspace: folders holding both MEM.md and MEM.config.md."""
    found, frontier = [], [Path(workspace)]
    for _ in range(depth + 1):
        following = []
        for folder in frontier:
            if (folder / "MEM.md").is_file() and (folder / "MEM.config.md").is_file():
                found.append(folder)
            try:
                following += [p for p in folder.iterdir() if p.is_dir() and p.name not in SKIP_FOLDERS]
            except OSError:
                pass
        frontier = following
    return found


def usage_counts(usage):
    """Anthropic input_tokens excludes cache reads and writes; mem-stats input is inclusive."""
    if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in USAGE_KEYS):
        return None
    read, write = usage["cache_read_input_tokens"], usage["cache_creation_input_tokens"]
    return {"input": usage["input_tokens"] + read + write, "cached_input": read,
            "cache_write": write, "output": usage["output_tokens"]}


def flatten(value):
    """Text of a string, a block ({"text"} / {"content"}) or a list of either; images and other data count as none."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(flatten(item) for item in value)
    if isinstance(value, dict):
        return flatten(value.get("text") if "text" in value else value.get("content"))
    return ""


def comparable(text):
    """Lower-case, forward slashes, Git Bash drive prefixes (/d/...) as d:/..."""
    text = str(text).replace("\\", "/").lower()
    return re.sub(r"(?<![\w:./])/([a-z])/", r"\1:/", text)


class Attributor:
    """Classifies what each transcript line puts in context, and splits MEM's share across cache buckets."""

    def __init__(self, kb_roots, encoding=None):
        self.roots = sorted({comparable(Path(r).resolve()).rstrip("/") for r in kb_roots}, key=len, reverse=True)
        self.encoding = encoding
        self.count_method = "tokenized:" + encoding if encoding else "estimated:characters/4"
        self.encoder = None

    def tokens(self, text):
        if not text:
            return 0
        if self.encoding:
            if self.encoder is None:
                import tiktoken
                self.encoder = tiktoken.get_encoding(self.encoding)
            return len(self.encoder.encode(text, disallowed_special=()))
        return math.ceil(len(text) / 4)

    def place(self, text, anywhere=False):
        """(origin, rest): origin is 'mem-core', an extension id, or None for a path (or, with anywhere, a command)
        outside every KB root; rest is what follows the root, i.e. the KB page for a path, in its own case."""
        original, text = str(text).replace("\\", "/"), comparable(text)
        original = original if len(original) == len(text) else text
        for root in self.roots:
            start = text.find(root) if anywhere else (0 if text.startswith(root) else -1)
            end = start + len(root)
            if start < 0 or (end < len(text) and text[end] in NAME_CHARS):
                continue
            match = re.match(r"/extensions/([a-z0-9][a-z0-9-]*)/", text[end:])
            return (match[1] if match else "mem-core"), original[end:].lstrip("/") or None
        return None, None

    def locate(self, text, anywhere=False):
        return self.place(text, anywhere)[0]

    def tool_target(self, name, arguments, cwd):
        """(origin, KB page) of a tool call; the page is <shell> or <search> when the call names no single page."""
        if not isinstance(arguments, dict):
            return None, None
        if name in COMMAND_TOOLS:
            command = arguments.get("command") or ""
            origin = self.locate(command, anywhere=True) or (self.locate(cwd) if cwd else None)
            return origin, "<shell>" if origin else None
        for key in PATH_KEYS:
            value = arguments.get(key)
            if isinstance(value, str) and value:
                absolute = re.match(r"^([a-z]:)?/", comparable(value))
                origin, page = self.place(value if absolute or not cwd else cwd + "/" + value)
                if name in ("Grep", "Glob"):
                    page = None
                return origin, (page or "<search>") if origin else None
        origin = self.locate(cwd) if name in ("Grep", "Glob") and cwd else None
        return origin, "<search>" if origin else None

    def instruction_target(self, item):
        origin, page = self.place(item.get("path") or "")
        if origin is None and any(m in (item.get("content") or "").lower() for m in POINTER_MARKERS):
            origin, page = "mem-core", "<instructions>"
        return origin, page

    def segments(self, record, tools):
        """[(tokens, origin, category, KB page)] this line adds to context, in order.

        tools: tool_use id -> (origin, page)."""
        cwd = record.get("cwd")
        if record.get("type") == "attachment":
            rendered = record.get("rendered")
            if not rendered:
                return []  # not injected: hook errors, prompt snapshots
            total, result = self.tokens(flatten(rendered)), []
            attachment = record.get("attachment") or {}
            if attachment.get("type") == "instructions":
                for item in attachment.get("files") or []:
                    origin, page = self.instruction_target(item)
                    if origin:
                        size = min(self.tokens(item.get("content") or ""), total - sum(n for n, *_ in result))
                        result.append((size, origin, "instructions", page))
            return [(total - sum(n for n, *_ in result), None, None, None)] + result
        if record.get("type") == "system":
            return []
        content = (record.get("message") or {}).get("content")
        if isinstance(content, str):
            return [(self.tokens(content), None, None, None)]
        result = []
        for block in content if isinstance(content, list) else []:
            kind = block.get("type") if isinstance(block, dict) else None
            if kind == "text":
                result.append((self.tokens(block.get("text")), None, None, None))
            elif kind == "thinking":
                result.append((self.tokens(block.get("thinking")), None, None, None))
            elif kind == "tool_use":
                origin, page = self.tool_target(block.get("name"), block.get("input"), cwd)
                tools[block.get("id")] = (origin, page)
                writes = origin is not None and block.get("name") in WRITE_TOOLS
                result.append((self.tokens(json.dumps(block.get("input"), ensure_ascii=False)),
                               *((origin, "kb_writes", page) if writes else (None, None, None))))
            elif kind == "tool_result":
                origin, page = tools.get(block.get("tool_use_id"), (None, None))
                result.append((self.tokens(flatten(block.get("content"))), origin,
                               "kb_tool_results" if origin else None, page))
        return result


class Context:
    """Context lines of one transcript: the parentUuid chain from a request back to its root is its prompt.

    Sizes are calibrated on measured usage. A request's own lines occupy its output_tokens (thinking included:
    it stays in context although the transcript keeps little of its text). The lines added between two requests
    on one chain occupy I(next) - I(previous) - output(previous); estimates only share that out among them.
    """

    PLAUSIBLE = (0.5, 5.0)  # measured/estimated outside this range falls back to the median measured so far
    DEFAULT_RATIO = 1.5  # characters/4 against Claude tokens, from this host's transcripts (median 1.57)

    def __init__(self, attributor):
        self.attributor, self.tools, self.lines, self.requests, self.owner = attributor, {}, {}, {}, {}
        self.ratios, self.sizes, self.calibrated = {}, {}, False
        self.groups = {"measured": 0, "fallback": 0}
        self.sources, self.tool_names = {}, {}  # uuid -> (source label, processed by sqz); tool_use id -> label
        self.listings, self.snapshots = {}, []  # uuid -> fixed-overhead attachment; (file index, overhead event)
        # Compactions: summary (anchor) uuid -> (head, tail) of the messages kept verbatim after it; preserved lines
        # first sent in a request's prompt -> that request.
        self.splices, self.joined = {}, {}

    def add(self, index, record):
        uuid = record.get("uuid")
        if not uuid or record.get("type") not in ("user", "assistant", "attachment", "system"):
            return
        self.lines[uuid] = (record.get("parentUuid"), self.attributor.segments(record, self.tools))
        segment = (record.get("compactMetadata") or {}).get("preservedSegment") \
            if record.get("subtype") == "compact_boundary" else None
        if isinstance(segment, dict) and all(isinstance(segment.get(k), str) for k in ("headUuid", "anchorUuid", "tailUuid")):
            self.splices[segment["anchorUuid"]] = (segment["headUuid"], segment["tailUuid"])
        attachment = record.get("attachment") if record.get("type") == "attachment" else None
        if isinstance(attachment, dict) and attachment.get("type") in LISTINGS and record.get("rendered"):
            self.listings[uuid] = {"sessionId": record.get("sessionId"), "timestamp": record.get("timestamp"),
                                   "attachment": {"type": attachment["type"]}}
        elif isinstance(attachment, dict) and attachment.get("type") == "prompt_snapshot" and attachment.get("tools"):
            self.snapshots.append((index, self.snapshot(record, attachment)))
        content = (record.get("message") or {}).get("content")
        blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
        label, processed = None, False
        if record.get("type") == "assistant":
            label = "assistant_output"
            for block in blocks:
                if block.get("type") == "tool_use":
                    self.tool_names[block.get("id")] = tool_label(block.get("name"))
        elif record.get("type") == "attachment":
            label = "attachment:" + safe(attachment.get("type") if isinstance(attachment, dict) else None)
        elif record.get("type") == "user":
            label = "user_message"
            results = [b for b in blocks if b.get("type") == "tool_result"]
            if results:
                label = "tool:" + self.tool_names.get(results[0].get("tool_use_id"), "unknown")
                processed = any(SQZ_MARKERS.search(flatten(b.get("content"))) for b in results)
        self.sources[uuid] = (label, processed)

    def snapshot(self, record, attachment):
        """Overhead event for the system prompt and tool definitions Claude Code recorded; estimates, not calibrated."""
        tokens = self.attributor.tokens
        items = {"system_prompt": tokens(flatten(attachment.get("systemPrompt")))}
        for tool in attachment["tools"] if isinstance(attachment["tools"], list) else []:
            if isinstance(tool, dict) and tool.get("name"):
                key = "tool:" + safe(tool["name"])
                items[key] = items.get(key, 0) + tokens(json.dumps(tool, ensure_ascii=False))
        return {"schema": SCHEMA, "id": "overhead:" + record.get("sessionId", "") + ":" + record["uuid"],
                "session": record.get("sessionId", ""), "kind": "overhead", "at": record.get("timestamp"),
                "source": "prompt_snapshot", "count_method": self.attributor.count_method, "items": items}

    def listing(self, uuid):
        """Overhead event for a listing attachment, sized like the rest of the prompt (calibrated)."""
        record = self.listings[uuid]
        kind = record["attachment"]["type"]
        return {"schema": SCHEMA, "id": "overhead:" + record.get("sessionId", "") + ":" + uuid,
                "session": record.get("sessionId", ""), "kind": "overhead", "at": record.get("timestamp"),
                "source": kind, "count_method": "calibrated:provider-usage+" + self.attributor.count_method,
                "items": {kind: math.floor(sum(n for n, *_ in self.segments(uuid)))}}

    def snapshot_before(self, index):
        """The latest prompt snapshot recorded before a file index: the tools in force for a request there."""
        found = None
        for position, event in self.snapshots:
            if position >= index:
                break
            found = event
        return found

    def request(self, request_id, lines, counts, thinking):
        self.requests[request_id] = {"lines": [r["uuid"] for r in lines if r.get("uuid")], "counts": counts,
                                     "thinking": min(thinking, counts["output"])}
        for uuid in self.requests[request_id]["lines"]:
            self.owner[uuid] = request_id

    def calibrate(self):
        """Measured/estimated ratio for every group of lines added between two requests on a chain.

        Requests are visited in file order and an unmeasurable group takes the median of the ratios measured
        before it, so a settled request's attribution never changes as the transcript grows.
        """
        measured, first = [], next(iter(self.requests), None)
        for request_id, request in self.requests.items():
            group, previous, known = [], None, []
            for uuid, preserved in self.ancestry(self.start(request_id)):
                if preserved:
                    # Kept across a compaction: lines already in an earlier prompt keep their size; lines never sent
                    # before (the results of the last turn before it) are new here and join the group.
                    if uuid in self.owner or uuid in self.ratios:
                        known.append(uuid)
                    else:
                        group.append(uuid)
                        self.joined[uuid] = request_id
                    continue
                if self.owner.get(uuid, request_id) != request_id:
                    previous = self.requests[self.owner[uuid]]
                    break
                group.append(uuid)
            estimate = sum(n for u in group for n, *_ in self.lines[u][1])
            ratio, added = None, None
            if previous and estimate:
                added = request["counts"]["input"] - previous["counts"]["input"] - previous["counts"]["output"]
            elif known and estimate and first != request_id:
                # First request after a compaction: no earlier prompt is a prefix of this one. What the summary side
                # adds is the input less the preserved lines and the fixed prefix (system prompt and tools) as
                # measured on the file's first request: the prefix of the last request before the compaction has
                # absorbed the estimation error of a long context, and would understate the summary side. The
                # unexplained prefix of such a request therefore equals the first one's by construction.
                added = request["counts"]["input"] - self.prefix(first) - sum(
                    n for u in known for n, *_ in self.segments(u))
            if added is not None and self.PLAUSIBLE[0] <= added / estimate <= self.PLAUSIBLE[1]:
                ratio = added / estimate
                measured.append(ratio)
            if estimate:
                self.groups["measured" if ratio else "fallback"] += 1
            if ratio is None:
                ratio = statistics.median(measured) if measured else self.DEFAULT_RATIO
            for uuid in group:
                self.ratios.setdefault(uuid, ratio)
        self.calibrated = True

    def start(self, request_id):
        """The newest line of a request's prompt: the parent of its first line."""
        request = self.requests[request_id]
        return self.lines.get(request["lines"][0], (None,))[0] if request["lines"] else None

    def ancestry(self, uuid):
        """(uuid, preserved) for the lines of a prompt, newest first, back to the root.

        After a compaction the chain runs from the summary (the anchor) back to the boundary, while the messages the
        compaction kept verbatim (head ... tail, still chained to the old context) follow the summary in the prompt:
        they are spliced in before the summary, flagged as preserved, whether the walk reaches the summary from a later
        line or starts on it."""
        stack, seen = [], set()
        while True:
            if uuid not in self.lines or uuid in seen:
                if not stack:
                    return
                uuid = stack.pop()[1]  # a segment cut short: carry on at its summary
                continue
            head, tail = self.splices.get(uuid, (None, None))
            if tail in self.lines and tail not in seen:
                stack.append((head, uuid))
                uuid = tail
                continue
            seen.add(uuid)
            yield uuid, bool(stack)
            if stack and uuid == stack[-1][0]:
                uuid = stack.pop()[1]
                continue
            uuid = self.lines[uuid][0]

    def prefix(self, request_id):
        """Input of a calibrated request that no line explains: the system prompt and tool definitions."""
        total = sum(n for u, _ in self.ancestry(self.start(request_id)) for n, *_ in self.segments(u))
        return self.requests[request_id]["counts"]["input"] - total

    def segments(self, uuid):
        """Calibrated (tokens, origin, category) of one line."""
        if uuid in self.sizes:
            return self.sizes[uuid]
        segments = self.lines[uuid][1]
        request_id = self.owner.get(uuid)
        if request_id is None:
            ratio = self.ratios.get(uuid, self.DEFAULT_RATIO)
            result = [(n * ratio, *rest) for n, *rest in segments]
        else:
            # Spread measured visible output over the request's estimated blocks; thinking is measured apart.
            request = self.requests[request_id]
            visible = sum(n for u in request["lines"] for n, *_ in self.lines[u][1])
            share = (request["counts"]["output"] - request["thinking"]) / visible if visible else 0.0
            result = [(n * share, *rest) for n, *rest in segments]
            if uuid == request["lines"][0]:
                result.insert(0, (float(request["thinking"] if visible else request["counts"]["output"]), None, None, None))
        self.sizes[uuid] = result
        return result

    def attribution(self, request_id):
        """MEM and extension buckets for a request, placing segments backwards from the end of its prompt."""
        if not self.calibrated:
            self.calibrate()
        request = self.requests[request_id]
        counts = request["counts"]
        cached, written, total = counts["cached_input"], counts["cache_write"], counts["input"]
        bounds = ((0, cached), (cached, cached + written), (cached + written, total))
        shares, categories, tail, overflow = {}, {}, 0.0, False
        for uuid, _ in self.ancestry(self.start(request_id)):
            if tail >= total:
                overflow = True  # calibrated content already fills the prompt before the chain's root
                break
            for size, origin, category, _ in reversed(self.segments(uuid)):
                high = total - tail
                tail += size
                if origin:
                    low = max(0.0, total - tail)
                    parts = [max(0.0, min(high, b) - max(low, a)) for a, b in bounds]
                    for key in ("mem-core", origin) if origin != "mem-core" else ("mem-core",):
                        current = shares.setdefault(key, [0.0, 0.0, 0.0])
                        for i, part in enumerate(parts):
                            current[i] += part
                    categories[category] = categories.get(category, 0.0) + sum(parts)
        outputs = {}
        for line in request["lines"]:
            for size, origin, category, _ in self.segments(line):
                if category == "kb_writes":
                    outputs[origin] = outputs.get(origin, 0) + size

        written_out = sum(outputs.values())
        # Estimated write sizes can exceed the measured output; shrink them together so parts stay within the whole.
        ratio = min(1.0, counts["output"] / written_out) if written_out else 0.0

        def buckets(key):
            read, write, fresh = (math.floor(v) for v in shares.get(key, (0, 0, 0)))
            out = written_out if key == "mem-core" else outputs.get(key, 0.0)
            return {"input": read + write + fresh, "cached_input": read, "cache_write": write,
                    "output": math.floor(out * ratio)}

        extensions = sorted((set(shares) | set(outputs)) - {"mem-core"})
        mem = buckets("mem-core")
        floors = {k: math.floor(v) for k, v in sorted(categories.items())}
        while sum(floors.values()) > mem["input"]:  # per-bucket flooring can leave mem input a token or two lower
            floors[max(floors, key=floors.get)] -= 1
        # What calibrated content does not explain is the system prompt and tool definitions (or estimate error).
        return {"mem": mem, "extensions": {e: buckets(e) for e in extensions}, "categories": floors,
                "prefix": max(0, round(total - tail)), "overflow": overflow}

    def composition(self, request_id):
        """Calibrated prompt content of a request by source, split into new (first time in a prompt) and carried.

        New is what entered since the previous request on the chain: the lines added in between and that request's
        own output. Everything older is carried, which is what cache reads pay for on every later request.
        """
        if not self.calibrated:
            self.calibrate()
        request = self.requests[request_id]
        sources, processed = {}, {}
        for uuid, phase in self.chain(request_id):
            label, by_sqz = self.sources.get(uuid, (None, False))
            size = sum(n for n, *_ in self.segments(uuid)) if label else 0
            if size:
                sources.setdefault(label, {"new": 0.0, "carried": 0.0})[phase] += size
                if by_sqz:
                    item = processed.setdefault("sqz", {"results": 0, "new": 0.0, "carried": 0.0})
                    item[phase] += size
                    item["results"] += phase == "new"
        total = sum(v["new"] + v["carried"] for v in sources.values())
        # Calibrated content rarely exceeds measured input; when it does, shrink it to fit rather than overstate.
        fit = min(1.0, request["counts"]["input"] / total) if total else 1.0
        return {"sources": {k: {p: math.floor(v[p] * fit) for p in ("new", "carried")} for k, v in sorted(sources.items())},
                "processed": {k: {"results": v["results"], "new": math.floor(v["new"] * fit),
                                  "carried": math.floor(v["carried"] * fit)} for k, v in processed.items()}}

    def chain(self, request_id):
        """(uuid, phase) for each line of a request's prompt, newest first; phase is 'new' until the lines that
        were already in the previous request on the chain, then 'carried'. Lines preserved across a compaction are
        carried, except those this request sent for the first time."""
        phase, previous = "new", None
        for uuid, preserved in self.ancestry(self.start(request_id)):
            if preserved:
                yield uuid, "new" if self.joined.get(uuid) == request_id else "carried"
                continue
            owner = self.owner.get(uuid)
            if phase == "new" and owner is not None and previous is None:
                previous = owner
            elif phase == "new" and previous is not None and owner != previous:
                phase = "carried"
            yield uuid, phase

    def breakdown(self, request_id):
        """Input no calibrated content explains (system prompt and tools), the fixed-overhead listings the prompt
        carries, and KB pages by new and carried tokens."""
        if not self.calibrated:
            self.calibrate()
        request = self.requests[request_id]
        total, pages, listings = 0.0, {}, []
        for uuid, phase in self.chain(request_id):
            segments = self.segments(uuid)
            total += sum(n for n, *_ in segments)
            if uuid in self.listings:
                listings.append(uuid)
            for size, _, _, page in segments:
                if page:
                    page = page if LABEL.fullmatch(page) else "<other>"
                    pages.setdefault(page, {"new": 0.0, "carried": 0.0})[phase] += size
        fit = min(1.0, request["counts"]["input"] / total) if total else 1.0
        return {"prefix": max(0, round(request["counts"]["input"] - total)), "listings": listings[::-1],
                "kb_pages": {k: {p: math.floor(v[p] * fit) for p in ("new", "carried")} for k, v in sorted(pages.items())}}


def slim(record):
    """What later stages need of an assistant line: identity, usage and the names of the tools it called."""
    message = record.get("message") or {}
    content = message.get("content")
    return {**{k: record.get(k) for k in ("uuid", "sessionId", "timestamp", "version", "entrypoint", "isSidechain",
                                          "agentId")},
            "message": {"model": message.get("model"), "usage": message.get("usage"),
                        "stop_reason": message.get("stop_reason"),
                        "content": [{"type": "tool_use", "name": b.get("name"), "id": b.get("id")} for b in content
                                    if isinstance(b, dict) and b.get("type") == "tool_use"]
                        if isinstance(content, list) else []}}


def parse(path, coverage, provider="anthropic", quiet=60, now=None, attributor=None, composition=False, stored=None):
    """Yield per settled request: usage, then MEM attribution (given an attributor), then composition and breakdown
    (if asked), each breakdown preceded by the overhead events it names that this parse has not yielded yet.

    stored(session, request_id) -> True skips a settled request whose events the ledger already holds: its estimates
    cannot change as the transcript grows, so only new requests are computed (the whole file is still read, since the
    context chain and calibration need every line)."""
    requests, last_turn, yielded, answered = {}, -1, set(), set()
    context = Context(attributor or Attributor([])) if attributor or composition else None
    # The project is the session's starting folder; a subagent transcript inherits its parent session's.
    parent = path.parent.parent.with_suffix(".jsonl") if path.parent.name == "subagents" else None
    project = (first_cwd(parent) if parent else None) or first_cwd(path) or first_cwd(path, main=False)
    project = project_path(project)
    agent_type = None
    try:  # a subagent transcript's agent-<id>.meta.json names its agent type (its description is not read)
        agent_type = json.loads(path.with_name(path.stem + ".meta.json").read_text(encoding="utf-8")).get("agentType")
    except (OSError, ValueError, AttributeError):
        pass
    stream = open(path, encoding="utf-8", errors="replace")
    for index, line in enumerate(stream):
        try:
            record = json.loads(line)
        except ValueError:
            coverage["unreadable_lines"] += 1
            continue
        if not isinstance(record, dict):
            coverage["unreadable_lines"] += 1
            continue
        if isinstance(record.get("sessionId"), str):
            coverage.setdefault("session_id", record["sessionId"])
        if isinstance(record.get("timestamp"), str) and record["timestamp"] > coverage.get("last_at", ""):
            coverage["last_at"] = record["timestamp"]
        if context:
            context.add(index, record)
        if record.get("type") in ("user", "assistant"):
            last_turn = index
        if record.get("type") == "user" and isinstance((record.get("message") or {}).get("content"), list):
            answered.update(b.get("tool_use_id") for b in record["message"]["content"]
                            if isinstance(b, dict) and b.get("type") == "tool_result")
        if record.get("type") == "system" and record.get("sessionId") and record.get("timestamp") and \
                not record.get("isSidechain"):
            subtype, meta = record.get("subtype"), record.get("compactMetadata") or {}
            if subtype == "compact_boundary" or (subtype == "local_command" and
                                                 (record.get("commandRun") or {}).get("command") == "clear"):
                event = {"schema": SCHEMA, "id": "lifecycle:" + record["sessionId"] + ":" + str(record.get("uuid")),
                         "session": record["sessionId"], "kind": "lifecycle", "at": record["timestamp"],
                         "event": "compaction" if subtype == "compact_boundary" else "clear"}
                if subtype == "compact_boundary":
                    event.update({k: meta.get(m) if type(meta.get(m)) is int else None for k, m in
                                  (("tokens_before", "preTokens"), ("tokens_after", "postTokens"),
                                   ("duration_ms", "durationMs"))}, trigger=meta.get("trigger"))
                coverage["lifecycle_events"] += 1
                yield event
        if record.get("type") != "assistant":
            continue
        message = record.get("message") or {}
        if message.get("model") == "<synthetic>" or not record.get("requestId"):
            coverage["synthetic_or_unidentified_lines"] += 1
            continue
        counts = usage_counts(message.get("usage"))
        if counts is None or not record.get("sessionId"):
            coverage["unrecognized_usage_lines"] += 1
            continue
        # Streaming writes one line per content block: input buckets repeat, output grows to the final line.
        entry = requests.setdefault(record["requestId"], {"inputs": set(), "lines": [], "first": index})
        entry["inputs"].add((counts["input"], counts["cached_input"], counts["cache_write"]))
        record = slim(record)
        entry["lines"].append(record)
        entry.update(last=index, record=record, counts=counts)
    stream.close()
    quiet_file = (now or time.time()) - path.stat().st_mtime >= quiet
    if context:
        for request_id, entry in requests.items():
            details = entry["record"]["message"]["usage"].get("output_tokens_details") or {}
            thinking = details.get("thinking_tokens")
            context.request(request_id, entry["lines"], entry["counts"], thinking if type(thinking) is int else 0)
    for request_id, entry in requests.items():
        record, usage = entry["record"], entry["record"]["message"]["usage"]
        stop = entry["record"]["message"].get("stop_reason")
        # Settled once the conversation moved past the request's final line, or it stopped and the file went quiet.
        if not (last_turn > entry["last"] or (stop and quiet_file)):
            coverage["requests_pending"] += 1
            continue
        if len(entry["inputs"]) > 1:
            coverage["requests_inconsistent_input"] += 1
            continue
        version = record.get("version") or "unknown"
        coverage["versions"][version] = coverage["versions"].get(version, 0) + 1
        session = record["sessionId"]
        coverage["sessions"].add(session)
        coverage["requests_emitted"] += 1
        if not stop:
            # No stop reason: the output count is a lower bound. Either the request was cut short, or it completed
            # (its tool calls were answered) but the transcript kept only the usage of its first streamed lines, as
            # subagent transcripts of several 2.1.x versions do.
            calls = [b.get("id") for line in entry["lines"] for b in line["message"]["content"]]
            completed = bool(calls) and all(c in answered for c in calls)
            coverage["requests_output_not_final" if completed else "requests_interrupted"] += 1
        if stored and stored(session, request_id):
            coverage["requests_already_stored"] += 1
            continue
        cache = usage.get("cache_creation") or {}
        tools = {k: v for k, v in (usage.get("server_tool_use") or {}).items() if type(v) is int and v > 0}
        event = {"schema": SCHEMA, "id": "usage:" + session + ":" + request_id, "session": session, "kind": "usage",
                 "request_id": request_id, "provider": provider, "model": record["message"].get("model") or "unknown",
                 "at": record.get("timestamp"), "usage": entry["counts"], "project": project,
                 "usage_detail": {"cache_write_1h": min(int(cache.get("ephemeral_1h_input_tokens") or 0),
                                                        entry["counts"]["cache_write"])},
                 # "not_available" reports no geography rather than one: kept unreported, so reports count it
                 # among default-tier assumptions instead of matching no price card.
                 "tier": {"service_tier": usage.get("service_tier"), "speed": usage.get("speed"),
                          "inference_geo": None if usage.get("inference_geo") == "not_available" else usage.get("inference_geo")},
                 # Without a stop reason the request was interrupted: its output count is a lower bound.
                 "output_final": bool(stop),
                 "client": {"name": CLIENT, "version": version, "entrypoint": record.get("entrypoint"),
                            "sidechain": bool(record.get("isSidechain")), "agent": record.get("agentId")}}
        if project is None:
            del event["project"]
        if agent_type and record.get("isSidechain"):
            event["client"]["agent_type"] = safe(agent_type)
        if tools:
            event["server_tool_use"] = tools
        yield event
        if attributor:
            estimate = context.attribution(request_id)
            stats = coverage["attribution"]
            stats["requests"] += 1
            stats["prefixes"].append(estimate.pop("prefix"))
            stats["requests_overflowing_input"] += estimate.pop("overflow")
            stats["mem_input"] += estimate["mem"]["input"]
            stats["input"] += entry["counts"]["input"]
            yield {"schema": SCHEMA, "id": "attribution:" + session + ":" + request_id + ":" + METHOD,
                   "session": session, "kind": "attribution", "request_id": request_id, "method": METHOD,
                   "count_method": "calibrated:provider-usage+" + attributor.count_method,
                   "kb_roots": len(attributor.roots), **estimate}
        if composition:
            coverage["compositions"] += 1
            yield {"schema": SCHEMA, "id": "composition:" + session + ":" + request_id + ":" + METHOD,
                   "session": session, "kind": "composition", "request_id": request_id, "method": METHOD,
                   **context.composition(request_id)}
            detail = context.breakdown(request_id)
            snapshot = context.snapshot_before(entry["first"])
            overhead = ([snapshot] if snapshot else []) + [context.listing(u) for u in detail.pop("listings")]
            for item in overhead:
                if item["id"] not in yielded:
                    yielded.add(item["id"])
                    coverage["overhead_events"] += 1
                    yield item
            calls = {}
            for line in entry["lines"]:
                for block in line["message"].get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name"):
                        calls[safe(block["name"])] = calls.get(safe(block["name"]), 0) + 1
            coverage["breakdowns"] += 1
            yield {"schema": SCHEMA, "id": "breakdown:" + session + ":" + request_id + ":" + METHOD,
                   "session": session, "kind": "breakdown", "request_id": request_id, "method": METHOD,
                   "count_method": "calibrated:provider-usage+" + context.attributor.count_method,
                   "kb_roots": len(context.attributor.roots),
                   "overhead": [item["id"] for item in overhead], "tools_called": dict(sorted(calls.items())), **detail}
    if attributor:
        if not context.calibrated:
            context.calibrate()  # every request was already stored: count the groups all the same
        for key, value in context.groups.items():
            coverage["attribution"]["groups_" + key] += value


def new_coverage(attributor=None):
    coverage = {"client": CLIENT, "tested_versions": [v + "x" for v in TESTED_VERSIONS], "files": 0,
                "sessions": set(), "requests_emitted": 0, "requests_pending": 0, "requests_inconsistent_input": 0,
                "synthetic_or_unidentified_lines": 0, "unrecognized_usage_lines": 0, "unreadable_lines": 0, "versions": {},
                "compositions": 0, "breakdowns": 0, "overhead_events": 0, "lifecycle_events": 0,
                "requests_interrupted": 0, "requests_output_not_final": 0, "conflicts": 0, "skipped_after_conflict": 0, "requests_already_stored": 0}
    if attributor:
        coverage["attribution"] = {"method": METHOD, "count_method": attributor.count_method, "kb_roots": attributor.roots,
                                   "requests": 0, "requests_overflowing_input": 0, "groups_measured": 0,
                                   "groups_fallback": 0, "prefixes": [], "mem_input": 0, "input": 0}
    return coverage


def merge(total, part):
    """Add one transcript's coverage counters to a running total."""
    for key, value in part.items():
        if type(value) is int:
            total[key] = total.get(key, 0) + value
        elif isinstance(value, set):
            total.setdefault(key, set()).update(value)
        elif isinstance(value, dict):
            merge(total.setdefault(key, {}), value)
        elif key == "prefixes":
            total.setdefault(key, []).extend(value)
        elif key == "kb_roots":  # attribution runs of several project groups: every root used
            total[key] = sorted(set(total.get(key, [])) | set(value))
        elif key == "last_at":
            total[key] = max(total.get(key) or "", value)
        else:
            total.setdefault(key, value)
    return total


# Counts that depend on how much of a run was incremental, not on the session: kept out of coverage events.
RUN_COUNTS = {"compositions", "breakdowns", "overhead_events", "requests_already_stored", "conflicts",
              "skipped_after_conflict"}


def coverage_event(session, part, context=None):
    """A session's coverage counts as a ledger event: counts only, replaced by the next run over the session. context
    records what the run computed (revision, KB roots...), so that a later run knows whether stored events match."""
    counts = {k: v for k, v in part.items() if type(v) is int and k not in RUN_COUNTS}
    for key in ("groups_measured", "groups_fallback"):
        if key in part.get("attribution", {}):
            counts["attribution_" + key] = part["attribution"][key]
    event = {"schema": SCHEMA, "id": "coverage:" + session + ":" + CLIENT, "session": session, "kind": "coverage",
             "client": CLIENT, "counts": dict(sorted(counts.items())), "context": context or {},
             "untested_versions": {safe(v, "unknown"): n for v, n in sorted(part["versions"].items())
                                   if not v.startswith(TESTED_VERSIONS)}}
    if part.get("last_at"):
        event["at"] = part["last_at"]
    return event


def project_groups(files):
    """Transcripts grouped by project folder (main transcripts and their subagent transcripts together), in order."""
    groups = {}
    for path in files:
        folder = path.parent.parent.parent if path.parent.name == "subagents" else path.parent
        groups.setdefault(folder, []).append(path)
    return list(groups.values())


def project_kb_roots(files):
    """KB roots under a project's folder: the working folder of the first main-chain line of its first transcript."""
    mains = [p for p in files if p.parent.name != "subagents"] or files
    folder = first_cwd(mains[0]) or first_cwd(mains[0], main=False)
    return find_kb_roots(folder) if folder and Path(folder).is_dir() else []


def stored_requests(collector, context, attribution, composition):
    """stored(session, request_id): True when the ledger holds every event this run would derive for the request,
    written by a run with the same context (read from the session's coverage event)."""
    cache = {}
    kinds = ["usage"] + (["attribution"] if attribution else []) + (["composition", "breakdown"] if composition else [])

    def ids(session):
        row = collector.db.execute("SELECT payload FROM events WHERE id=?",
                                   ("coverage:" + session + ":" + CLIENT,)).fetchone()
        if row is None or json.loads(row[0]).get("context") != context:
            return None
        found = set()
        for kind in kinds:  # primary-key ranges, not a scan of the session column
            prefix = kind + ":" + session + ":"
            found.update(r[0] for r in collector.db.execute("SELECT id FROM events WHERE id >= ? AND id < ?",
                                                            (prefix, prefix[:-1] + ";")))
        return found

    def stored(session, request_id):
        if session not in cache:
            cache[session] = ids(session)
        found = cache[session]
        return found is not None and all(
            (kind + ":" + session + ":" + request_id + ("" if kind == "usage" else ":" + METHOD)) in found
            for kind in kinds)
    return stored


def finish(coverage):
    coverage.pop("session_id", None)
    coverage.pop("last_at", None)
    coverage["sessions"] = len(coverage["sessions"])
    coverage["untested_versions"] = sorted(v for v in coverage["versions"] if not v.startswith(TESTED_VERSIONS))
    stats = coverage.get("attribution")
    if stats:
        # Input not explained by calibrated content: the system prompt and tools. A stable value is a good sign.
        prefixes = sorted(stats.pop("prefixes"))
        stats["unexplained_prefix_tokens"] = {"p10": prefixes[len(prefixes) // 10], "median": statistics.median(prefixes),
                                              "p90": prefixes[len(prefixes) * 9 // 10]} if prefixes else None
        stats["mem_input_share_percent"] = round(stats["mem_input"] / stats["input"] * 100, 3) if stats["input"] else None
    return coverage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--workspace", type=Path, help="workspace folder opened in Claude Code")
    source.add_argument("--transcript", type=Path, action="append", help="explicit transcript file; repeatable")
    source.add_argument("--all", action="store_true", help="every project under the Claude Code projects folder")
    parser.add_argument("--projects-dir", type=Path, help="default: $CLAUDE_CONFIG_DIR/projects or ~/.claude/projects")
    parser.add_argument("--session", help="only this session id")
    parser.add_argument("--provider", default="anthropic", help="label for the billing provider (e.g. bedrock, vertex)")
    parser.add_argument("--quiet", type=float, default=60, help="seconds without writes before a final request counts as settled")
    parser.add_argument("--kb-root", type=Path, action="append", default=[],
                        help="KB root for MEM attribution; repeatable. With --workspace, roots inside it are found too")
    parser.add_argument("--no-attribution", action="store_true", help="no MEM attribution events")
    parser.add_argument("--no-composition", action="store_true",
                        help="no per-request context composition, breakdown or overhead events")
    parser.add_argument("--encoding", help="tiktoken encoding for segment estimates (default: characters/4)")
    parser.add_argument("--db", type=Path, help="ingest into this mem-stats ledger instead of writing JSONL to stdout")
    parser.add_argument("--full", action="store_true",
                        help="with --db, recompute requests whose events the ledger already holds (default: skip them)")
    parser.add_argument("--find-kb", action="store_true",
                        help="per project, also use the KB roots found under the folder its sessions started in")
    args = parser.parse_args()
    root = args.projects_dir or projects_dir()
    if args.transcript:
        files = args.transcript
    elif args.all:
        files = [f for folder in sorted(p for p in root.iterdir() if p.is_dir()) for f in transcripts(folder)]
    else:
        folder = root / workspace_folder(args.workspace.resolve())
        if not folder.is_dir():
            raise ValueError("no Claude Code transcripts for this workspace: " + str(folder))
        files = transcripts(folder)
    collector = None
    if args.db:
        import importlib.util
        spec = importlib.util.spec_from_file_location("mem_stats", Path(__file__).with_name("stats.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        collector = module.Collector(args.db, batch=module.BATCH)
    coverage, sessions = new_coverage(), {}

    def deliver(event, part):
        if collector:
            outcome = collector.offer(event)
            part["conflicts"] += outcome == "conflict"
            part["skipped_after_conflict"] += outcome == "skipped"
        else:
            sys.stdout.write(json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n")
    try:
        # Each project (a folder of the projects directory) has its own KB roots, hence its own attributor, run
        # context and incremental skip set: a project without a KB never blanks the estimates of one with it.
        for files_of in project_groups(files):
            roots = [] if args.no_attribution else args.kb_root + (
                find_kb_roots(args.workspace) if args.workspace else []) + (
                project_kb_roots(files_of) if args.find_kb else [])
            attributor = Attributor(roots, args.encoding) if roots else None
            context = {"revision": REVISION, "kb_roots": len(attributor.roots) if attributor else 0,
                       "attribution": int(bool(attributor)), "composition": int(not args.no_composition),
                       "tokenized": int(bool(args.encoding))}
            stored = None if args.full or not collector else stored_requests(collector, context, bool(attributor),
                                                                              not args.no_composition)
            for path in files_of:
                if args.session and args.session not in (path.stem, path.parent.parent.name):
                    continue
                part = new_coverage(attributor)
                part["files"] = 1
                for event in parse(path, part, args.provider, args.quiet, attributor=attributor,
                                   composition=not args.no_composition, stored=stored):
                    deliver(event, part)
                session = part.get("session_id") or (
                    path.parent.parent.name if path.parent.name == "subagents" else path.stem)
                merge(sessions.setdefault(session, ({}, context))[0], part)
                merge(coverage, part)
        # One coverage event per session, after its transcripts (main and subagents) were all read.
        for session, (part, context) in sessions.items():
            deliver(coverage_event(session, part, context), coverage)
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
