"""Claude Code SessionStart hook: resume a new session from a handoff note the agent wrote before `/clear`.

The agent writes the note only after the user confirms a restart; the user types `/clear`; this hook injects the
note into the fresh session as `additionalContext`, then marks it consumed so it is never injected twice. It also
carries over a prompt the advisor held back after a long pause (--held), with the snapshot of the last exchanges
kept beside it when no handoff note exists, deleting both once delivered. With --compact, a session restarted by a
compaction (source `compact`) gets a short pointer to re-orient from the knowledge base. A note older
than --max-age, or a session started for another reason, is left alone. Standard library only; on any error it
prints nothing and the session starts normally.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

LIMIT = 9000  # additionalContext strings are capped at 10,000 characters; beyond that, inject a pointer instead
CAP = 9800  # the whole injected context, below that cap


def log(path, entry):
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError:
        pass


def fresh(path, max_age):
    return path is not None and path.is_file() and time.time() - path.stat().st_mtime <= max_age


def compact_pointer(kb_root):
    """A few hundred characters: where to re-orient after a compaction. Paths only, never page contents, and no
    guess at the current task, which the hook cannot know."""
    where = ("Re-read " + str(kb_root / "MEM.index.md") + " and the resume point of the latest log in "
             + str(kb_root / "logs") + "." if kb_root is not None else
             "If this workspace has a MEM knowledge base, re-read its MEM.index.md and the resume point of the latest "
             "log.")
    return ("The conversation was just compacted: earlier text, knowledge base pages included, is gone and only the "
            "summary remains. " + where + " For the work in progress the summary is more recent than the knowledge "
            "base; for decisions, conventions and stable context the knowledge base is authoritative. Re-read other "
            "pages only when the next step needs them.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, help="handoff note written by the agent")
    parser.add_argument("--held", type=Path, help="prompt the advisor held back after a long pause")
    parser.add_argument("--kb-root", type=Path, help="KB to re-orient from when only a held prompt is carried over")
    parser.add_argument("--sources", default="clear", help="comma-separated SessionStart sources to act on")
    parser.add_argument("--compact", action="store_true",
                        help="after a compaction (source compact), inject a pointer to re-orient from the KB")
    parser.add_argument("--max-age", type=float, default=7200, help="seconds after which a note is stale")
    parser.add_argument("--log", type=Path, help="append one JSON line per event (no content)")
    args = parser.parse_args()
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        source = event.get("source")
        entry.update(event=event.get("hook_event_name"), source=source, session=event.get("session_id"),
                     fields=sorted(event.keys()))
        note, held = args.handoff, args.held
        has_note, has_held = fresh(note, args.max_age), fresh(held, args.max_age)
        if source == "compact" and args.compact:
            context = compact_pointer(args.kb_root)
            sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                                "additionalContext": context}}, ensure_ascii=False))
            entry.update(decision="pointer", chars=len(context))
        elif source not in args.sources.split(","):
            entry["decision"] = "source-not-handled"
        elif not has_note and not has_held:
            entry["decision"] = "stale-handoff" if note is not None and note.is_file() else "no-handoff"
        else:
            parts, confirm = [], []
            consumed = note.with_name(note.stem + ".consumed-" + time.strftime("%Y%m%d-%H%M%S") + note.suffix) \
                if has_note else None
            if has_note:
                text = note.read_text(encoding="utf-8")
                if len(text) > LIMIT:  # point at the name the note will have once marked consumed below
                    text = ("A handoff note from the previous session is too long to inline; read it first: "
                            + str(consumed.resolve()))
                written = time.strftime("%H:%M", time.localtime(note.stat().st_mtime))
                parts.append("Resuming from the previous session's handoff note (written before /clear at the user's "
                             "confirmation). Continue from it; do not ask the user to repeat it.\n\n" + text)
                confirm.append("the handoff note written at " + written + " was restored")
            if has_held:
                kept = json.loads(held.read_text(encoding="utf-8"))
                prompt, recent = kept.get("prompt") or "", "" if has_note else (kept.get("snapshot") or "").strip()
                orient = "" if has_note else (
                    " If this workspace has a MEM knowledge base, re-orient from it first: read its MEM.index.md and "
                    "the resume point of the latest log." if args.kb_root is None else
                    " Re-orient from the KB first: read " + str(args.kb_root / "MEM.index.md") +
                    " and the resume point of the latest log.")
                parts.append("Before /clear, mem-optimize held back the user's message so that it would not re-send "
                             "the previous session's whole context." + orient + " Treat the message as the user's "
                             "request and act on it at the user's next input, whatever that input says:\n\n<<<\n" +
                             prompt + "\n>>>")
                confirm.append("their held message was carried over")
                room = CAP - sum(len(p) + 2 for p in parts) - 300  # the closing instruction
                if recent and room > 500:
                    if len(recent) > room:  # keep the latest turns
                        recent = recent[-room:]
                        recent = recent[recent.find("\n\nUser: ") + 2:] if "\n\nUser: " in recent else recent
                    parts.append("The previous session's last exchanges, extracted mechanically from its transcript "
                                 "when the message was held (oldest first; the KB stays authoritative where they "
                                 "differ):\n\n" + recent)
                    confirm.append("a snapshot of the last exchanges was restored")
            # The VS Code extension does not display systemMessage: the agent's first reply is the visible confirmation.
            context = "\n\n".join(parts) + ("\n\nOpen your first reply with one short line telling the user that " +
                                           " and ".join(confirm) + ".")
            # systemMessage reaches the user only on clients that display it
            notice = "MEM: " + " and ".join(confirm) + "."
            sys.stdout.write(json.dumps({"systemMessage": notice,
                                         "hookSpecificOutput": {"hookEventName": "SessionStart",
                                                                "additionalContext": context}}, ensure_ascii=False))
            if has_note:
                note.rename(consumed)
            if has_held:
                held.unlink()  # the user's own words: not kept once delivered
            entry.update(decision="injected", chars=len(context), note=has_note, held=has_held)
    except Exception as error:  # never break a session start
        entry["decision"] = "error: " + type(error).__name__
    log(args.log, entry)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
