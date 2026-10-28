"""Prompt hook for Claude Code, Codex and the clients in clients.py: tell the agent when the session's context has
grown costly, and optionally stop the first prompt after a long pause. Claude Code, Codex and Factory Droid accept the
same hook output, and the transcript format is recognised from its lines; --client names another client (Droid, Qwen
Code, OpenCode and Kilo through their plugin), whose payload and answer clients.py translates. A payload from a client other than --client (Cursor and GitHub Copilot also run Claude Code's hooks) gets
nothing.

Reads the size of the last request from the session transcript. Below the advise threshold it prints nothing, so it
adds no tokens. At or above it, it adds one short line of context asking the agent to propose a guided restart at the
next natural breakpoint, and says it again only when the level rises (advise, then insist). The agent relays the
advice: the VS Code extension does not show a hook's systemMessage.

With --pause-stop, a prompt sent after the prompt cache has expired, on a context of at least --pause-min tokens, is
blocked once: sending it would re-write the whole context into the cache. Its text is kept beside --held, one file
per session (held-prompt-<hash>.json), with the session's working directory, for the SessionStart hook to carry into a
fresh session in the same folder after /clear (or a new conversation), and the user
is told, in --lang, how to choose: /clear
(recommended) or the same message again within --resend-window seconds, which then passes. Since the model is not
called, no agent can write a handoff note: instead a mechanical snapshot of the last exchanges (the user's prompts,
the agent's final replies, the files it changed), at most --snapshot-chars long, is kept with the held prompt.

What was told to each session is kept beside --state, one file per session (advisor-state/<hash>.json), so that
sessions running at once in several projects never rewrite each other's. Standard library only; on any error it
prints nothing and the prompt goes through unchanged.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
from decimal import Decimal
from pathlib import Path

CHUNK = 1 << 18
MAX_SCAN = 1 << 24  # stop looking for a usage line after 16 MB from the end of the transcript
KEEP = 7 * 86400  # forget sessions not seen for a week
SNAPSHOT_SCAN = 1 << 22  # the snapshot reads the last 4 MB of the transcript
EDITORS = {"Edit": "file_path", "MultiEdit": "file_path", "Write": "file_path", "NotebookEdit": "notebook_path"}
LEVELS = ("none", "advise", "insist")
STOP = {
    "en": ("mem-optimize: {pause} since the last reply, longer than the prompt cache lasts. Sending this message "
           "in this session would re-write the whole context into the cache: ~{size}k tokens{cost}.\n"
           "(A, recommended) {action}, then send any short message: your message will be carried automatically "
           "into the new session, where you can resume work without this cost.\n"
           "(B) Send a message again within {window} minutes, this one or another, to continue here anyway."),
    "it": ("mem-optimize: sono passati {pause} dall'ultima risposta, più della durata della cache. Inviare questo "
           "messaggio in questa sessione riscriverebbe in cache tutto il contesto: ~{size}k token{cost}.\n"
           "(A, consigliato) {action}, poi invia un messaggio qualsiasi: il tuo messaggio verrà automaticamente "
           "portato nella nuova sessione, dove potrai riprendere il lavoro senza questa spesa.\n"
           "(B) Invia di nuovo un messaggio entro {window} minuti, questo o un altro, per continuare qui comunque."),
}
COST = {"en": ", about {currency} {amount:.2f} at API rates", "it": ", circa {currency} {amount:.2f} a tariffe API"}
# How the user starts a fresh session: a slash command (/clear, OpenCode's /new).
ACTION = {"en": "Type {command}", "it": "Scrivi {command}"}


def load_clients():
    spec = importlib.util.spec_from_file_location("mem_optimize_clients", Path(__file__).with_name("clients.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def action(lang, restart):
    return ACTION[lang].format(command=restart)


def state_file(clients, state, session):
    """One file per session in a folder beside --state (advisor-state/): prompts of sessions running at once, in any
    project, never read and rewrite one shared file."""
    return state.with_suffix("") / (clients.digest(session or "", 16) + ".json")


def load_state(path, legacy, session):
    """This session's state; the first time, its entry in the single file written before 0.2.1."""
    for source, pick in ((path, lambda found: found), (legacy, lambda found: found.get(session))):
        try:
            found = pick(json.loads(source.read_text(encoding="utf-8")))
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(found, dict):
            return found
    return {}


def drop_legacy(shared, session):
    """Delete the single held-prompt file of 0.2.0 when the stop it records was this session's: a resend or a new stop
    here settles it, and it must not be carried over after /clear as well."""
    try:
        if json.loads(shared.read_text(encoding="utf-8")).get("session") == session:
            shared.unlink()
    except (OSError, ValueError, AttributeError):
        pass


def save_state(path, legacy, mine, now):
    """Write this session's state atomically, through a temporary file of its own; forget sessions not seen for
    KEEP, and the pre-0.2.1 file once it is that old."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("%s.%d.%s.tmp" % (path.stem, os.getpid(), os.urandom(4).hex()))
    temporary.write_text(json.dumps(mine, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)
    for old in list(path.parent.glob("*.json")) + [legacy]:
        try:
            if now - old.stat().st_mtime >= KEEP:
                old.unlink()
        except OSError:  # gone already, or another session's hook got there first
            pass


def log(path, entry):
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError:
        pass


def backwards(path):
    """The transcript's lines, last first, up to MAX_SCAN bytes from the end."""
    with open(path, "rb") as stream:
        stream.seek(0, 2)
        end = stream.tell()
        position, tail = end, b""
        while position > 0 and end - position < MAX_SCAN:
            step = min(CHUNK, position)
            position -= step
            stream.seek(position)
            lines = (stream.read(step) + tail).split(b"\n")
            tail = lines.pop(0) if position > 0 else b""  # possibly cut: completed by the next chunk
            yield from reversed(lines)


def last_usage(path, codex_ttl=1800):
    """The last request's usage, normalized: {tokens, at, model, usage (for the price card), ttl or None}.

    Claude Code: the last main-session assistant line carrying usage. Codex: the last token_usage_record, or the last
    event_msg/token_count of older rollouts, with the model of the latest turn_context; its cache lifetime is not in
    the rollout, so codex_ttl applies (OpenAI: 30 minutes for GPT-5.6 and later)."""
    found = None
    for line in backwards(path):
        if found is not None:
            if b'"turn_context"' in line:
                try:
                    found["model"] = (json.loads(line).get("payload") or {}).get("model")
                except ValueError:
                    continue
                return found
            continue
        if b'"usage"' in line and b'"assistant"' in line:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            message = record.get("message") or {}
            if (record.get("type") == "assistant" and not record.get("isSidechain")
                    and isinstance(message.get("usage"), dict) and message.get("model") != "<synthetic>"):
                return {"tokens": context_tokens(message["usage"]), "at": record.get("timestamp"),
                        "model": message.get("model"), "usage": message["usage"], "ttl": None}
        elif b'"token_usage_record"' in line or b'"token_count"' in line:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            payload = record.get("payload") or {}
            if record.get("type") == "token_usage_record":
                usage = payload.get("usage")
            elif record.get("type") == "event_msg" and payload.get("type") == "token_count":
                usage = (payload.get("info") or {}).get("last_token_usage")
            else:
                continue
            if isinstance(usage, dict) and isinstance(usage.get("input_tokens"), int):
                # Codex input_tokens already includes cached input.
                found = {"tokens": usage["input_tokens"] + (usage.get("output_tokens") or 0),
                         "at": record.get("timestamp"), "model": None, "usage": {}, "ttl": codex_ttl}
    return found


def context_tokens(usage):
    """What the next request re-sends: the last prompt (inclusive input) plus the last answer."""
    keys = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens")
    return sum(usage.get(k) or 0 for k in keys if isinstance(usage.get(k), int))


def cache_ttl(usage, default):
    """Seconds the prompt cache lasts, from the last request's cache writes (1h or 5m); default when it wrote none."""
    creation = usage.get("cache_creation") or {}
    if (creation.get("ephemeral_1h_input_tokens") or 0) > 0:
        return 3600
    if (creation.get("ephemeral_5m_input_tokens") or 0) > 0:
        return 300
    return default


def card_for(model, usage, prices):
    if prices is None:
        return None
    speed = usage.get("speed") or "standard"
    return next((c for c in json.loads(prices.read_text(encoding="utf-8-sig"))
                 if c.get("model") == model and (c.get("speed") or "standard") == speed), None)


def rate_cost(card, key, tokens):
    """(currency, amount) at one per-million rate of a price card, or None."""
    if card is None or not card.get(key):
        return None
    return card.get("currency", "USD"), Decimal(str(card[key])) * tokens / Decimal(1_000_000)


def advice(level, tokens, cost, handoff=None, restart="/clear"):
    size = "~%dk tokens" % round(tokens / 1000)
    price = "" if cost is None else ", about %s %.2f per request at API rates" % (cost[0], cost[1])
    if level == "insist":
        text = ("mem-optimize advisor: this session's context is %s%s, past the insist threshold. Before starting new "
                "work, propose a guided restart to the user in one short line." % (size, price))
    else:
        text = ("mem-optimize advisor: this session's context is %s%s; every request re-sends it. At the next natural "
                "breakpoint, not in the middle of a change, propose a guided restart to the user in one short line."
                % (size, price))
    # Self-contained, so that the restart works in projects whose KB does not carry the extension's instructions.
    steps = (" Guided restart, only after the user agrees: update the project's knowledge base resume point if it has "
             "one; ")
    if handoff is not None:
        steps += ("write a handoff note to " + handoff.as_posix() + " (state, decisions made, next step, files to "
                  "read; plain Markdown, under 8,000 characters); ")
    return text + steps + "then ask the user to type " + restart + " and send any message to resume."


def clip(text, limit):
    """Head and tail of a text: a final reply's proposal or question is usually at its end."""
    text = text.strip()
    if len(text) <= limit:
        return text
    half = (limit - 5) // 2
    return text[:half].rstrip() + " […] " + text[-half:].lstrip()


def turns(path):
    """The main session's recent turns, oldest first: prompt, final reply, files changed."""
    with open(path, "rb") as stream:
        stream.seek(0, 2)
        start = max(0, stream.tell() - SNAPSHOT_SCAN)
        stream.seek(start)
        lines = stream.read().split(b"\n")
    if start:
        lines.pop(0)  # possibly cut
    found = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict) or record.get("isSidechain") or record.get("isMeta"):
            continue
        if record.get("type") == "response_item":  # Codex
            codex_turn(record.get("payload") or {}, found)
            continue
        content = (record.get("message") or {}).get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
        if not isinstance(blocks, list):
            continue
        if record.get("type") == "user" and not record.get("isCompactSummary"):
            # system reminders, IDE selections and slash commands arrive as tagged text: not the user's words
            texts = [b.get("text") or "" for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
            prompt = "\n".join(t for t in texts if t.strip() and not t.lstrip().startswith("<"))
            if prompt.strip():
                found.append({"prompt": prompt, "reply": "", "files": []})
        elif record.get("type") == "assistant" and found:
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and (block.get("text") or "").strip():
                    found[-1]["reply"] = block["text"]
                elif block.get("type") == "tool_use" and block.get("name") in EDITORS:
                    target = (block.get("input") or {}).get(EDITORS[block["name"]])
                    if target and target not in found[-1]["files"]:
                        found[-1]["files"].append(target)
    return found


PATCHED = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", re.M)


def codex_turn(payload, found):
    """One Codex response item into the turns: a user message opens a turn; the final answer and apply_patch
    targets fill it. Environment context and other tagged input are not the user's words."""
    if payload.get("type") == "message":
        texts = [c.get("text") or "" for c in payload.get("content") or [] if isinstance(c, dict)]
        if payload.get("role") == "user":
            prompt = "\n".join(t for t in texts if t.strip() and not t.lstrip().startswith("<"))
            if prompt.strip():
                found.append({"prompt": prompt, "reply": "", "files": []})
        elif payload.get("role") == "assistant" and found and payload.get("phase") != "commentary":
            text = "\n".join(t for t in texts if t.strip())
            if text.strip():
                found[-1]["reply"] = text
    elif payload.get("type") in ("custom_tool_call", "function_call") and found:
        source = payload.get("input") or payload.get("arguments") or ""
        for target in PATCHED.findall(source if isinstance(source, str) else ""):
            if target.strip() not in found[-1]["files"]:
                found[-1]["files"].append(target.strip())


def snapshot(found, budget):
    """The latest of the turns found that fit in budget characters, rendered oldest first; empty when none fit."""
    parts = []
    for turn in reversed(found):
        lines = ["User: " + clip(turn["prompt"], 600)]
        if turn["files"]:
            lines.append("Files changed: " + ", ".join(turn["files"][:10]) + (" …" if len(turn["files"]) > 10 else ""))
        if turn["reply"]:
            lines.append("Agent's final reply: " + clip(turn["reply"], 1400))
        part = "\n".join(lines)
        if sum(len(p) + 2 for p in parts) + len(part) > budget:
            break
        parts.append(part)
    return "\n\n".join(reversed(parts))


def duration(seconds):
    hours, minutes = divmod(int(seconds) // 60, 60)
    return "%dh%02d" % (hours, minutes) if hours else "%d min" % minutes


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--advise", type=int, default=400_000, help="context tokens at which to advise a restart")
    parser.add_argument("--insist", type=int, default=600_000, help="context tokens at which to insist")
    parser.add_argument("--no-advice", action="store_true", help="never advise a restart (pause stop only)")
    parser.add_argument("--handoff", type=Path, help="where the agent writes the handoff note before /clear")
    parser.add_argument("--state", type=Path, required=True,
                        help="what was told per session: one file per session in the folder of the same name")
    parser.add_argument("--prices", type=Path, help="mem-stats price card, to show API-equivalent costs")
    parser.add_argument("--pause-stop", action="store_true", help="stop the first prompt after the cache expired")
    parser.add_argument("--pause-min", type=int, default=200_000, help="context tokens at which a pause stops a prompt")
    parser.add_argument("--held", type=Path,
                        help="where stopped prompts are kept, one per session beside it, for the SessionStart hook")
    parser.add_argument("--resend-window", type=int, default=600, help="seconds within which a resend passes")
    parser.add_argument("--ttl", type=int, default=3600, help="cache lifetime when the transcript does not show it")
    parser.add_argument("--codex-ttl", type=int, default=1800, help="cache lifetime for Codex sessions (OpenAI)")
    parser.add_argument("--pause-after", type=int, help="treat this many idle seconds as a long pause (live tests)")
    parser.add_argument("--snapshot-chars", type=int, default=6000,
                        help="size of the snapshot of recent exchanges kept with a held prompt (0: none)")
    parser.add_argument("--lang", choices=sorted(STOP), default="en", help="language of the message shown to the user")
    parser.add_argument("--log", type=Path, help="append one JSON line per prompt (no content)")
    parser.add_argument("--client", default="claude", help="the client running the hook (see clients.py)")
    parser.add_argument("--restart", default="/clear",
                        help="the slash command that starts a fresh session")
    args = parser.parse_args()
    if args.pause_stop and args.held is None:
        parser.error("--pause-stop needs --held")
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        clients = load_clients()
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        why = clients.foreign(args.client, event)
        if why:
            entry["decision"] = why
            return
        info = clients.normalized(args.client, event)
        session, transcript = info["session"], info["transcript"]
        entry.update(session=session, client=args.client, cwd=info["cwd"])
        recorded = args.state.with_name("usage-recorded")  # Qwen Code's Stop hook writes one file per session there
        if event.get("hook_event_name") == "Stop":  # not a prompt: remember the usage, say nothing
            entry["decision"] = "recorded" if clients.record_usage(recorded, event) else "no-usage-in-stop"
            return
        if not info["typed"]:  # a continuation (Qwen: tool result, retry): never stopped, held or advised
            entry["decision"] = "not-a-user-prompt"
            return
        written = bool(transcript) and Path(transcript).is_file()
        record = None
        if written and args.client in clients.OPENCODE_FAMILY:
            record = clients.opencode_usage(transcript, session, args.codex_ttl)
        elif written:
            record = last_usage(Path(transcript), args.codex_ttl)
            if record is None and args.client not in ("claude", "codex"):
                record = clients.generic_usage(backwards(Path(transcript)), transcript)
        if record is None and args.client == "qwen":
            record = clients.recorded_usage(recorded, session)
        if record is None and args.client == "droid" and transcript:
            record = clients.droid_usage(transcript)
        if record is None:  # a new session's first prompt: nothing written yet
            entry["decision"] = "no-usage" if written else "no-transcript"
            return
        usage, model, tokens = record["usage"], record["model"], record["tokens"]
        ttl = record["ttl"] or cache_ttl(usage, args.ttl)
        own = state_file(clients, args.state, session)
        mine = load_state(own, args.state, session)
        now = time.time()
        mine["seen"] = now
        # This session's held prompt: a stop elsewhere never overwrites it, a resend here never deletes another's.
        held = clients.held_file(args.held, session) if args.held else None
        entry["tokens"] = tokens
        output = None
        at = clients.instant(record.get("at"))
        idle = now - at if at else 0
        if args.pause_stop and tokens >= args.pause_min and idle >= (args.pause_after or ttl):
            entry["idle_seconds"] = round(idle)
            if now - mine.get("stopped", 0) <= args.resend_window:
                mine.pop("stopped")  # (B): the user chose to continue here
                held.unlink(missing_ok=True)
                drop_legacy(args.held, session)  # the stop may have been recorded by 0.2.0
                entry["decision"] = "resent"
            else:
                card = card_for(model, usage, args.prices)
                cost = rate_cost(card, "cache_write_1h" if ttl == 3600 else "cache_write", tokens)
                # cwd: a new conversation (not /clear) takes the prompt only in the same folder
                kept = {"session": session, "at": now, "prompt": info["prompt"], "cwd": info["cwd"]}
                if args.snapshot_chars > 0:
                    try:
                        found = (clients.opencode_turns(transcript, session)
                                 if args.client in clients.OPENCODE_FAMILY else turns(Path(transcript)))
                        kept["snapshot"] = snapshot(found, args.snapshot_chars)
                    except Exception as error:  # the held prompt matters more than the snapshot
                        entry["snapshot"] = "error: " + type(error).__name__
                    else:
                        entry["snapshot"] = len(kept["snapshot"])
                held.parent.mkdir(parents=True, exist_ok=True)
                drop_legacy(args.held, session)
                held.write_text(json.dumps(kept, ensure_ascii=False), encoding="utf-8")
                mine["stopped"] = now
                text = STOP[args.lang].format(
                    pause=duration(idle), size=round(tokens / 1000), window=args.resend_window // 60,
                    action=action(args.lang, args.restart),
                    cost="" if cost is None else COST[args.lang].format(currency=cost[0], amount=cost[1]))
                output = clients.prompt_output(args.client, block=text)
                entry["decision"] = "stopped"
        if output is None and args.no_advice:
            entry.setdefault("decision", "silent")
        elif output is None:
            level = "insist" if tokens >= args.insist else "advise" if tokens >= args.advise else "none"
            told = mine.get("level", "none")
            # Say it once per level; a context that shrank below the threshold (compaction) starts over.
            mine["level"] = level if level == "none" or LEVELS.index(level) > LEVELS.index(told) else told
            entry.update(level=level, told=told)
            if level != "none" and LEVELS.index(level) > LEVELS.index(told):
                cost = rate_cost(card_for(model, usage, args.prices), "cached_input", tokens)
                # Each conversation has a note of its own, named after its folder: the session start delivers only
                # this folder's notes.
                note = clients.project_note(args.handoff, info["cwd"], session)
                output = clients.prompt_output(args.client, context=advice(level, tokens, cost, note, args.restart))
                entry["decision"] = "advised"
            else:
                entry.setdefault("decision", "silent")
        save_state(own, args.state, mine, now)
        if output is not None:
            sys.stdout.write(json.dumps(output, ensure_ascii=False))
    except Exception as error:  # never block or alter a prompt by accident
        entry["decision"] = "error: " + type(error).__name__
    finally:
        log(args.log, entry)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
