"""Client adapters shared by mem-optimize's hooks: what each client sends, where its usage is, what it accepts back.

Claude Code, Codex, Factory Droid and Qwen Code share one hook format (`session_id`, `transcript_path`,
`hookSpecificOutput`). OpenCode and Kilo Code (an OpenCode fork, CLI and VS Code extension) have no command hooks: the plugin
mem-optimize writes (`opencode-plugin.js`) calls the runners with a Claude-style event naming the session and the
client's database, and maps the answer back. Qwen Code's Stop hook reports the last request's input tokens: the prompt
hook records them (`record_usage`) and reads them back when the transcript carries none.

Other clients read Claude Code's settings files and run its hooks with payloads of their own (Cursor with third-party
hooks on; GitHub Copilot reads `.claude/settings*.json`): `foreign` recognises them, and the hooks then do nothing.

Loaded by path from the hooks (`python -I` keeps the runner folder off sys.path). Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from contextlib import closing
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

CLAUDE_STYLE = ("claude", "codex", "droid", "qwen")
OPENCODE_FAMILY = ("opencode", "kilo")  # plugins, sessions in SQLite
CLIENTS = CLAUDE_STYLE + OPENCODE_FAMILY
# Clients whose /clear can be linked to the session it ended: Claude Code runs a SessionEnd hook (reason clear) and
# then SessionStart (source clear) from the same client process, one per chat (measured 2026-10-29).
LINKED = ("claude",)
# Processes between a hook and its client: the shells it runs through and the interpreter launchers.
INTERMEDIATE = ("bash", "sh", "dash", "zsh", "fish", "ksh", "cmd", "powershell", "pwsh", "conhost", "env", "py",
                "python", "pythonw")
# Keys only other clients send: Cursor, Antigravity, GitHub Copilot (camelCase or VS Code-compatible formats). Cursor
# and Antigravity are not supported (they cannot carry both the advice and the stop message), but Cursor runs Claude
# Code's hooks.
FOREIGN_KEYS = ("cursor_version", "conversation_id", "conversationId", "sessionId", "workspacePaths",
                "initial_prompt", "initialPrompt", "opencode_db")
OPENCODE_EDITORS = ("edit", "write", "patch", "multiedit")


def foreign(client, event):
    """Why this payload does not come from `client`, or None."""
    if not isinstance(event, dict):
        return "foreign:not-an-object"
    if client in CLAUDE_STYLE:
        found = next((k for k in FOREIGN_KEYS if k in event), None)
        if found:
            return "foreign:" + found
        if event.get("source") == "new":  # GitHub Copilot's SessionStart source
            return "foreign:source-new"
        return None
    if client in OPENCODE_FAMILY:
        return None if event.get("opencode_db") else "foreign:not-" + client
    return "foreign:unknown-client"


def normalized(client, event):
    """{session, transcript, prompt, cwd, source, typed}. `typed` is False for a prompt event that is not something
    the user sent: Qwen Code also runs UserPromptSubmit on tool results and other continuations, whose `prompt` is the
    model-bound text; only `submitted_prompt`, present on user submissions alone and before any command expansion, is
    the user's (its absence means unavailable, never a fallback to `prompt`)."""
    if client in OPENCODE_FAMILY:
        return {"session": event.get("session_id") or "", "transcript": database(event.get("opencode_db")),
                "prompt": event.get("prompt") or "", "cwd": event.get("cwd"), "source": event.get("source"),
                "typed": True}
    if client == "qwen" and event.get("hook_event_name") == "UserPromptSubmit":
        typed = isinstance(event.get("submitted_prompt"), str)
        prompt = event["submitted_prompt"] if typed else ""
    else:
        typed, prompt = True, event.get("prompt") or ""
    return {"session": event.get("session_id") or "", "transcript": event.get("transcript_path"), "prompt": prompt,
            "cwd": event.get("cwd"), "source": event.get("source"), "typed": typed}


def prompt_output(client, block=None, context=None):
    """The prompt hook's answer: block with a message to the user, or add context for the model."""
    if client == "droid" and context and not block:  # Factory documents it at the top level for this event
        return {"additionalContext": context}
    if block:
        return {"decision": "block", "reason": block}
    if context:
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}
    return None


def session_output(client, context, notice=None):
    output = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
    return {"systemMessage": notice, **output} if notice else output


def folder(path):
    return os.path.normcase(os.path.normpath(path)) if path else None


def digest(text, length):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def project_note(base, cwd, session=None):
    """A handoff note of one working directory: handoff-<12 hex of the folder>-<8 hex of the session>.md beside the
    base path. The advisor names it, so a note written for one project is never delivered in another, and two
    conversations in one folder never overwrite each other's. Without a cwd, None: the base path itself is never
    used (every project would read it)."""
    if base is None or not cwd:
        return None
    name = base.stem + "-" + digest(folder(cwd), 12) + ("-" + digest(session, 8) if session else "")
    return base.with_name(name + base.suffix)


def project_notes(base, cwd):
    """The notes not yet consumed of one working directory: every session's, and the folder's own of 0.2.0."""
    if base is None or not cwd or not base.parent.is_dir():
        return []
    prefix = base.stem + "-" + digest(folder(cwd), 12)
    return sorted(p for p in base.parent.glob(prefix + "*" + base.suffix)
                  if ".consumed-" not in p.name and p.stem[len(prefix):len(prefix) + 1] in ("", "-"))


def held_file(base, session):
    """The prompt held for one session: held-prompt-<16 hex>.json beside the base path, so that a stop in one session
    never overwrites, and a resend never deletes, another session's."""
    return base.with_name(base.stem + "-" + digest(session or "", 16) + base.suffix)


def held_files(base):
    """Every held prompt waiting beside the base path, the base path itself included (one shared file before 0.2.1);
    not one already delivered by path (renamed .consumed-<stamp>)."""
    if base is None or not base.parent.is_dir():
        return []
    return sorted(p for p in base.parent.glob(base.stem + "*" + base.suffix) if ".consumed-" not in p.name
                  and (p == base or p.stem[len(base.stem):len(base.stem) + 1] == "-"))


def parents(depth=12):
    """[(pid, name)] from this process's parent upwards, names lower-case without .exe; [] when unknown."""
    table = {}
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class Entry(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                        ("szExeFile", ctypes.c_wchar * 260)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        snapshot = kernel.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
        if snapshot in (None, wintypes.HANDLE(-1).value):
            return []
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        try:
            found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while found:
                table[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile)
                found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel.CloseHandle(snapshot)
    chain, pid = [], os.getppid()
    while pid > 1 and len(chain) < depth:
        if os.name == "nt":
            if pid not in table:
                break
            parent, name = table[pid]
        else:
            try:  # Linux: "pid (name) state ppid ..."
                stat = Path("/proc/%d/stat" % pid).read_text()
                name, parent = stat[stat.index("(") + 1:stat.rindex(")")], int(stat[stat.rindex(")") + 2:].split()[1])
            except (OSError, ValueError, IndexError):
                try:  # macOS and other systems without /proc
                    out = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True,
                                         text=True, timeout=5).stdout.strip().split(None, 1)
                    parent, name = int(out[0]), os.path.basename(out[1])
                except (OSError, ValueError, IndexError, subprocess.SubprocessError):
                    break
        name = name.lower()
        chain.append((pid, name[:-4] if name.endswith(".exe") else name))
        pid = parent
    return chain


def client_process():
    """The client process running this hook, as "<pid>:<name>": the first ancestor that is not a shell or an
    interpreter launcher. Two hooks of one Claude Code chat share it; another chat has its own. None when unknown."""
    for pid, name in parents():
        base = name.rstrip("0123456789.")
        if base not in INTERMEDIATE and not base.startswith("python"):
            return "%d:%s" % (pid, name)
    return None


def instant(value):
    """Epoch seconds from an ISO 8601 string or a number (milliseconds when it is that large), or None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value / 1000 if value > 1e11 else float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# --- transcripts in formats not read natively (Droid, Qwen) -----------------------------------------------------

def tokens_of(usage):
    """Context tokens from a usage object in any of the common shapes, or None."""
    if not isinstance(usage, dict):
        return None

    def number(*keys):
        return sum(usage.get(k) or 0 for k in keys if isinstance(usage.get(k), int))

    if isinstance(usage.get("input_tokens"), int):
        # Anthropic: input excludes the cached part
        if "cache_read_input_tokens" in usage or "cache_creation_input_tokens" in usage:
            return number("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens")
        return number("input_tokens", "output_tokens")  # OpenAI: input includes cached input
    if isinstance(usage.get("inputTokens"), int):
        return number("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "outputTokens")
    if isinstance(usage.get("promptTokenCount"), int):  # Gemini: the prompt includes cached content
        return number("promptTokenCount", "candidatesTokenCount")
    if isinstance(usage.get("prompt_tokens"), int):
        return number("prompt_tokens", "completion_tokens")
    if isinstance(usage.get("input"), int) and isinstance(usage.get("output"), int):  # OpenCode style
        cache = usage.get("cache") if isinstance(usage.get("cache"), dict) else {}
        return usage["input"] + usage["output"] + sum(v for v in cache.values() if isinstance(v, int))
    return None


def usage_in(value, depth=0):
    """The first usage object found in a transcript record, searched a few levels deep."""
    if depth > 5:
        return None
    if isinstance(value, dict):
        for key in ("usage", "usageMetadata", "usage_metadata", "tokenUsage", "token_usage", "tokens"):
            found = tokens_of(value.get(key))
            if found:
                return found
        for item in value.values():
            if isinstance(item, (dict, list)):
                found = usage_in(item, depth + 1)
                if found:
                    return found
    elif isinstance(value, list):
        for item in value[-20:]:
            found = usage_in(item, depth + 1)
            if found:
                return found
    return None


def generic_usage(lines, path):
    """The last request's usage from a JSONL transcript whose format is not known in detail: the last record that
    carries a usage object. Its time is the record's own, or the file's last write."""
    for line in lines:
        if b"oken" not in line and b"sage" not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        tokens = usage_in(record)
        if tokens:
            at = None
            if isinstance(record, dict):
                at = next((instant(record.get(k)) for k in ("timestamp", "time", "createdAt", "created_at")
                           if instant(record.get(k)) is not None), None)
            return {"tokens": tokens, "at": at or Path(path).stat().st_mtime, "model": None, "usage": {}, "ttl": None}
    return None


# --- Qwen Code: usage from the Stop hook ---------------------------------------------------------------------------

def usage_file(folder, session):
    """One file per session, so that sessions running at once never rewrite each other's record."""
    return Path(folder) / (hashlib.sha1(session.encode("utf-8")).hexdigest()[:16] + ".json")


def record_usage(folder, event, keep=7 * 86400):
    """Remember a Stop event's input tokens for its session; True when there were any to keep. Each write goes to a
    temporary file of its own and replaces the session's file atomically; records older than `keep` are dropped."""
    tokens = event.get("input_tokens")
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0:
        return False
    folder, now = Path(folder), datetime.now().timestamp()
    folder.mkdir(parents=True, exist_ok=True)
    target = usage_file(folder, event.get("session_id") or "")
    temporary = target.with_name("%s.%d.%s.tmp" % (target.stem, os.getpid(), os.urandom(4).hex()))
    temporary.write_text(json.dumps({"tokens": tokens, "at": now}), encoding="utf-8")
    os.replace(temporary, target)
    for old in folder.glob("*.json"):
        try:
            if now - old.stat().st_mtime >= keep:
                old.unlink()
        except OSError:  # another session got there first
            pass
    return True


def recorded_usage(folder, session):
    try:
        found = json.loads(usage_file(folder, session).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(found, dict) or not isinstance(found.get("tokens"), int):
        return None
    return {"tokens": found["tokens"], "at": found.get("at"), "model": None, "usage": {}, "ttl": None}


# --- Factory Droid: usage beside the transcript ----------------------------------------------------------------------

def droid_usage(transcript):
    """The last request's usage of a Droid session. Its transcript (<id>.jsonl) carries none; <id>.settings.json beside
    it has `lastCallTokenUsage` (the last request) and `tokenUsage` (the session's running total, not the context).
    Measured with droid 0.249.0. Its time is the file's last write."""
    path = Path(transcript).with_suffix(".settings.json")
    try:
        last = json.loads(path.read_text(encoding="utf-8")).get("lastCallTokenUsage") or {}
        # Anthropic-style split, as in its running total: input, cache reads and cache writes are separate counts
        tokens = sum(last.get(k) or 0 for k in ("inputTokens", "cacheReadTokens", "cacheCreationTokens", "outputTokens")
                     if isinstance(last.get(k), int) and not isinstance(last.get(k), bool))
    except (OSError, ValueError, AttributeError):
        return None
    if not tokens:
        return None
    return {"tokens": tokens, "at": path.stat().st_mtime, "model": None, "usage": {}, "ttl": None}


# --- OpenCode and Kilo: sessions live in SQLite --------------------------------------------------------------------

def database(path):
    """The client's database: the file named, or, for a data folder (Kilo's file name is not documented), the most
    recently written *.db in it that has OpenCode's session and message tables. A string, or None."""
    if not path or path == ":memory:":  # an in-memory database: nothing to read from outside the client
        return None
    path = Path(path)
    if not path.is_dir():
        return str(path)
    for candidate in sorted(path.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with closing(opencode_connect(candidate)) as connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        except sqlite3.Error:
            continue
        if {"session", "message", "part"} <= tables:
            return str(candidate)
    return None


def opencode_connect(db):
    """A read-only connection to OpenCode's database, which OpenCode keeps writing meanwhile (WAL); close it."""
    uri = "file:" + quote(Path(db).resolve().as_posix(), safe="/:") + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=2)


def opencode_ttl(model, codex_ttl):
    model = (model or "").lower()
    if "claude" in model:
        return 300  # OpenCode marks Anthropic prompts with the default 5-minute cache
    if "gpt" in model or "codex" in model:
        return codex_ttl
    return None


def opencode_usage(db, session, codex_ttl=1800):
    """The session's last request: input, cached input and output of the last assistant message that ran. A
    compaction message's output is the summary, which is all the next request carries."""
    with closing(opencode_connect(db)) as connection:
        rows = connection.execute("SELECT data, time_created FROM message WHERE session_id = ? "
                                  "ORDER BY time_created DESC LIMIT 200", (session,)).fetchall()
    for data, created in rows:
        try:
            message = json.loads(data)
        except ValueError:
            continue
        if message.get("role") != "assistant":
            continue
        usage = message.get("tokens") or {}
        tokens = tokens_of(usage)
        if not tokens:
            continue  # a request that failed before running (no credit, network) costs nothing
        if message.get("mode") == "compaction" or message.get("summary") is True:
            tokens = usage.get("output") or tokens
        times = message.get("time") or {}
        model = message.get("modelID")
        return {"tokens": tokens, "at": instant(times.get("completed") or times.get("created") or created),
                "model": model, "usage": {}, "ttl": opencode_ttl(model, codex_ttl)}
    return None


def opencode_has_messages(db, session):
    with closing(opencode_connect(db)) as connection:
        row = connection.execute("SELECT 1 FROM message WHERE session_id = ? LIMIT 1", (session,)).fetchone()
    return row is not None


def opencode_turns(db, session):
    """The session's recent turns, oldest first: prompt, final reply, files changed."""
    with closing(opencode_connect(db)) as connection:
        messages = connection.execute("SELECT id, data FROM message WHERE session_id = ? "
                                      "ORDER BY time_created DESC LIMIT 200", (session,)).fetchall()[::-1]
        parts = {}
        for message_id, data in connection.execute("SELECT message_id, data FROM part WHERE session_id = ? "
                                                   "ORDER BY time_created, id", (session,)):
            parts.setdefault(message_id, []).append(data)
    found = []
    for message_id, data in messages:
        try:
            message = json.loads(data)
            pieces = [json.loads(p) for p in parts.get(message_id, [])]
        except ValueError:
            continue
        texts = [p.get("text") or "" for p in pieces if p.get("type") == "text" and not p.get("synthetic")]
        if message.get("role") == "user":
            prompt = "\n".join(t for t in texts if t.strip())
            if prompt.strip():
                found.append({"prompt": prompt, "reply": "", "files": []})
        elif message.get("role") == "assistant" and found:
            if any(t.strip() for t in texts):
                found[-1]["reply"] = [t for t in texts if t.strip()][-1]
            for piece in pieces:
                if piece.get("type") == "tool" and piece.get("tool") in OPENCODE_EDITORS:
                    target = ((piece.get("state") or {}).get("input") or {}).get("filePath")
                    if target and target not in found[-1]["files"]:
                        found[-1]["files"].append(target)
    return found
