"""Session-start hook for Claude Code, Codex and the clients in clients.py: resume a new session from a handoff note
the agent wrote before `/clear`.

The agent writes the note only after the user confirms a restart; the user types `/clear`; this hook injects the
note into the fresh session as `additionalContext`, then marks it consumed so it is never injected twice. It also
carries over a prompt the advisor held back after a long pause (--held), with the snapshot of the last exchanges
kept beside it when no handoff note exists, deleting both once delivered. With --compact, a session restarted by a
compaction (source `compact`) gets a short pointer to re-orient from the knowledge base. A note older
than --max-age, or a session started for another reason, is left alone.

The hooks are global, so everything is matched to the session's working directory, on every source: the advisor
names one note per conversation after its folder (handoff-<hash of the folder>-<hash of the session>.md beside
--handoff), and a held prompt (held-prompt-<hash of the session>.json beside --held) records its folder. The --handoff
path itself, which every project read before 0.2.1, is never delivered: a fresh one is only logged. When several
conversations of one folder left a restart, the hook lists them and the agent asks the user which to resume; nothing
is consumed then. A user who opens a new conversation instead of typing `/clear` (source `startup`: the VS Code
new-chat button, Codex `/new`) gets the same carry-over, but only from what is younger than --startup-max-age.
Clients without `/clear` (OpenCode's and Kilo's /new: --client) always start that way; an OpenCode or Kilo session
that already has messages is being resumed, not started. Standard library only; on any error it prints nothing and
the session starts normally.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

LIMIT = 9000  # additionalContext strings are capped at 10,000 characters; beyond that, inject a pointer instead
CAP = 9800  # the whole injected context, below that cap
KEEP = 7 * 86400  # a held message delivered by path is deleted after a week if the agent did not


def log(path, entry):
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError:
        pass


def load_clients():
    spec = importlib.util.spec_from_file_location("mem_optimize_clients", Path(__file__).with_name("clients.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fresh(path, max_age):
    return path is not None and path.is_file() and time.time() - path.stat().st_mtime <= max_age


def folder(path):
    return os.path.normcase(os.path.normpath(path)) if path else None


def held_here(held, cwd):
    """Whether the held prompt was stopped in this session's working directory (prompts held before the cwd was
    recorded do not qualify)."""
    try:
        kept = json.loads(held.read_text(encoding="utf-8")).get("cwd")
    except (OSError, ValueError, AttributeError):
        return False
    return kept is not None and folder(kept) == folder(cwd)


def consumed_name(path):
    """The name a note takes once delivered: a free one, even when the same note was consumed earlier this second."""
    stamp, number = path.stem + ".consumed-" + time.strftime("%Y%m%d-%H%M%S"), 1
    target = path.with_name(stamp + path.suffix)
    while target.exists():
        number += 1
        target = path.with_name("%s-%d%s" % (stamp, number, path.suffix))
    return target


def choices(notes, helds, restart):
    """Several conversations of this folder left a restart: list them, with what the agent needs to load the one the
    user picks. Nothing is consumed here: the others may belong to conversations still open."""
    lines = []
    for note in notes:
        try:
            first = next((line.strip("# ").strip() for line in note.read_text(encoding="utf-8").splitlines()
                          if line.strip()), "")
        except OSError:
            continue
        lines.append("- Handoff note written at %s: %s\n  file: %s (once used, rename it to %s)" % (
            time.strftime("%H:%M", time.localtime(note.stat().st_mtime)), first[:150], note.resolve().as_posix(),
            consumed_name(note).name))
    for held in helds:
        try:
            prompt = " ".join((json.loads(held.read_text(encoding="utf-8")).get("prompt") or "").split())
        except (OSError, ValueError, AttributeError):
            continue
        lines.append("- Message held at %s: \"%s\"\n  file: %s (JSON: \"prompt\" is the message, \"snapshot\" the "
                     "last exchanges; once used, delete the file)" % (
                         time.strftime("%H:%M", time.localtime(held.stat().st_mtime)),
                         prompt[:200] + ("…" if len(prompt) > 200 else ""), held.resolve().as_posix()))
    head = ("Before " + restart + ", different conversations in this working directory each left a restart for "
            "mem-optimize to carry over. Open your first reply by showing the user this list and asking which one to "
            "resume; act on none of them until the user answers. Then read only the chosen file and continue from it; "
            "leave the others untouched, since they may belong to conversations still open.\n\n")
    return (head + "\n".join(lines))[:CAP]


def same_origin(clients, base, cwd, note, held):
    """Whether a note and a held message are one restart: the advisor names a note after its session, and the held
    message records its own. A note named otherwise (0.2.0's, or one from note-path) cannot be shown to be."""
    try:
        session = json.loads(held.read_text(encoding="utf-8")).get("session")
    except (OSError, ValueError, AttributeError):
        return False
    return bool(session) and note == clients.project_note(base, cwd, session)


def restore(note, held, restart, startup, claude_style, kb_root):
    """The context carrying one restart over, within CAP. The held message always arrives whole: inline, or by the
    path it will be renamed to. The note comes next, inline or by path; the snapshot gets what room is left.
    Returns (context, notice, {"note", "held": inlined?, "note_to", "held_to": names once consumed})."""
    kept = json.loads(held.read_text(encoding="utf-8")) if held is not None else {}
    prompt = kept.get("prompt") or ""
    recent = "" if note is not None else (kept.get("snapshot") or "").strip()
    text = note.read_text(encoding="utf-8") if note is not None else ""
    note_to = consumed_name(note) if note is not None else None
    held_to = consumed_name(held) if held is not None else None
    written = time.strftime("%H:%M", time.localtime(note.stat().st_mtime)) if note is not None else ""
    for note_inline, held_inline in ((True, True), (False, True), (True, False), (False, False)):
        if note_inline and len(text) > LIMIT:
            continue
        parts, confirm = [], []
        if note is not None:
            opened = ("" if not startup else
                      " The user opened a new conversation instead of typing /clear: if the note is about another "
                      "project than this session's working directory, ignore it and say so." if claude_style else
                      " This is a new conversation: if the note is about another project than this session's "
                      "working directory, ignore it and say so.")
            body = text if note_inline else ("A handoff note from the previous session is too long to inline; read it "
                                             "first: " + str(note_to.resolve()))
            parts.append("Resuming from the previous session's handoff note (written before " + restart + " at the "
                         "user's confirmation). Continue from it; do not ask the user to repeat it." + opened + "\n\n" +
                         body)
            confirm.append("the handoff note written at " + written + " was restored")
        if held is not None:
            orient = "" if note is not None else (
                " If this workspace has a MEM knowledge base, re-orient from it first: read its MEM.index.md and "
                "the resume point of the latest log." if kb_root is None else
                " Re-orient from the KB first: read " + str(kb_root / "MEM.index.md") +
                " and the resume point of the latest log.")
            message = ("\n\n<<<\n" + prompt + "\n>>>" if held_inline else
                       " The message is too long to inline: read it whole first, the \"prompt\" field of " +
                       str(held_to.resolve()) + " (delete that file once it has been acted on).")
            parts.append("Before " + restart + ", mem-optimize held back the user's message so that it would not "
                         "re-send the previous session's whole context." + orient + " Treat the message as the user's "
                         "request and act on it at the user's next input, unless that input clearly asks for "
                         "something else (then follow the new input):" + message)
            confirm.append("their held message was carried over")
            room = CAP - sum(len(p) + 2 for p in parts) - 300  # the closing instruction
            if recent and room > 500:
                cut = recent
                if len(cut) > room:  # keep the latest turns
                    cut = cut[-room:]
                    cut = cut[cut.find("\n\nUser: ") + 2:] if "\n\nUser: " in cut else cut
                parts.append("The previous session's last exchanges, extracted mechanically from its transcript "
                             "when the message was held (oldest first; the KB stays authoritative where they "
                             "differ):\n\n" + cut)
                confirm.append("a snapshot of the last exchanges was restored")
        # The VS Code extension does not display systemMessage: the agent's first reply is the visible confirmation.
        context = "\n\n".join(parts) + ("\n\nOpen your first reply with one short line telling the user that " +
                                       " and ".join(confirm) + ".")
        if len(context) <= CAP:
            break
    # systemMessage reaches the user only on clients that display it
    notice = "MEM: " + " and ".join(confirm) + "."
    return context, notice, {"note": note_inline, "held": held_inline, "note_to": note_to, "held_to": held_to}


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
    parser.add_argument("--sources", default="clear,startup", help="comma-separated SessionStart sources to act on")
    parser.add_argument("--compact", action="store_true",
                        help="after a compaction (source compact), inject a pointer to re-orient from the KB")
    parser.add_argument("--max-age", type=float, default=7200, help="seconds after which a note is stale")
    parser.add_argument("--startup-max-age", type=float, default=900,
                        help="seconds after which a new conversation (source startup) no longer takes the note")
    parser.add_argument("--log", type=Path, help="append one JSON line per event (no content)")
    parser.add_argument("--client", default="claude", help="the client running the hook (see clients.py)")
    args = parser.parse_args()
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        clients = load_clients()
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        entry.update(client=args.client, fields=sorted(event.keys()) if isinstance(event, dict) else None)
        why = clients.foreign(args.client, event)
        if why:
            entry["decision"] = why
            return
        info = clients.normalized(args.client, event)
        source, cwd, transcript, session = info["source"], info["cwd"], info["transcript"], info["session"]
        entry.update(event=event.get("hook_event_name"), source=source, session=session, cwd=cwd)
        base, startup = args.handoff, source == "startup"
        claude_style = args.client in clients.CLAUDE_STYLE
        # Claude Code, Codex and Droid always name the transcript: a startup payload without one is another client's.
        evidence = bool(transcript) or not claude_style
        if args.client in clients.OPENCODE_FAMILY and startup and transcript and clients.opencode_has_messages(
                transcript, session):
            startup, source = False, "resume"
        # A new conversation, not /clear, takes only what its folder left moments ago. On every source, only what was
        # left in this session's folder: the advisor names one note per conversation after its folder, and a held
        # prompt records its folder.
        window = args.startup_max_age if startup else args.max_age
        usable = evidence or not startup
        notes = [n for n in clients.project_notes(base, cwd) if fresh(n, window)] if usable else []
        helds = [h for h in clients.held_files(args.held) if fresh(h, window) and held_here(h, cwd)] if usable else []
        if fresh(base, args.max_age):  # the one note every project read before 0.2.1: never delivered
            entry["legacy_note"] = "ignored"
        if args.held is not None:  # held messages delivered by path that the agent did not delete: the user's words
            for old in args.held.parent.glob(args.held.stem + "*.consumed-*" + args.held.suffix):
                if time.time() - old.stat().st_mtime >= KEEP:
                    old.unlink(missing_ok=True)
        restart = "the restart" if startup else "/clear"
        if source == "compact" and args.compact:
            context = compact_pointer(args.kb_root)
            sys.stdout.write(json.dumps(clients.session_output(args.client, context), ensure_ascii=False))
            entry.update(decision="pointer", chars=len(context))
        elif source not in args.sources.split(","):
            entry["decision"] = "source-not-handled"
        elif not notes and not helds:
            elsewhere = any(fresh(h, window) for h in clients.held_files(args.held))
            entry["decision"] = ("no-transcript" if not usable else "other-project" if elsewhere else
                                 "legacy-note-ignored" if entry.get("legacy_note") else
                                 "stale-handoff" if clients.project_notes(base, cwd) else "no-handoff")
        elif len(notes) > 1 or len(helds) > 1 or (notes and helds and not same_origin(
                clients, base, cwd, notes[0], helds[0])):
            # several conversations of this folder left a restart (or a note and a held message that cannot be shown
            # to be one restart): the user picks
            context = choices(notes, helds, restart)
            notice = "MEM: several restarts were left in this folder; choose which one to resume."
            sys.stdout.write(json.dumps(clients.session_output(args.client, context, notice), ensure_ascii=False))
            entry.update(decision="ambiguous", chars=len(context), note=len(notes), held=len(helds))
        else:
            note, held = (notes or [None])[0], (helds or [None])[0]
            context, notice, inline = restore(note, held, restart, startup, claude_style, args.kb_root)
            # Consumed before printing: a rename that fails must not leave anything to be injected again. A held message
            # too long to inline is kept, renamed, for the agent to read whole.
            if note is not None:
                note.rename(inline["note_to"])
            if held is not None and not inline["held"]:
                held.rename(inline["held_to"])
            sys.stdout.write(json.dumps(clients.session_output(args.client, context, notice), ensure_ascii=False))
            if held is not None and inline["held"]:
                held.unlink()  # the user's own words: not kept once delivered
            entry.update(decision="injected", chars=len(context), note=note is not None, held=held is not None,
                         inline=inline["note"] and inline["held"])
    except Exception as error:  # never break a session start
        entry["decision"] = "error: " + type(error).__name__
    finally:
        log(args.log, entry)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
