"""Session hooks for Claude Code, Codex and the clients in clients.py: carry a conversation over a restart.

What a conversation leaves for the session that continues it is a resume package (resume.py): the snapshot of its
last exchanges, the handoff note the agent wrote after the user agreed to a restart, and the message the advisor held
back after a long pause (--held). On Claude Code, the SessionEnd of a /clear (reason clear) saves the snapshot, with
the client process the chat runs in, and adopts a note the conversation wrote; the SessionStart that follows (source
clear, same process, under a second later) restores that package and only that one. --restore governs a package
that holds only a snapshot: auto (inject it), offer (one line, loaded on request) or off; a note or a held message is
always carried over. Where the link fails although expected, or on clients without it (Codex, Droid, Qwen, OpenCode,
Kilo), one package of this folder is restored and several are listed for the user to pick one (resume.py claim).

The hooks are global, so everything is matched to the session's working directory, on every source. The --handoff
path itself, which every project read before 0.2.1, is never delivered: a fresh one is only logged. A user who opens
a new conversation instead of typing /clear (source startup: the VS Code new-chat button, Codex /new) gets notes and
held messages younger than --startup-max-age, never a snapshot. Clients without /clear (OpenCode's and Kilo's /new:
--client) always start that way; an OpenCode or Kilo session that already has messages is being resumed. With
--compact, a session restarted by a compaction (source compact) gets a short pointer to re-orient from the knowledge
base. Standard library only; on any error it prints nothing and the session starts normally.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path


def log(path, entry):
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError:
        pass


def load(name):
    spec = importlib.util.spec_from_file_location("mem_optimize_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    parser.add_argument("--packages", type=Path, help="folder of resume packages (snapshots saved at /clear)")
    parser.add_argument("--restore", choices=("auto", "offer", "off"), default="auto",
                        help="what /clear does with a package holding only a snapshot")
    parser.add_argument("--snapshot-chars", type=int, default=6000, help="size of the snapshot saved at /clear")
    parser.add_argument("--kb-root", type=Path, help="KB to re-orient from when only a held prompt is carried over")
    parser.add_argument("--sources", default="clear,startup", help="comma-separated SessionStart sources to act on")
    parser.add_argument("--compact", action="store_true",
                        help="after a compaction (source compact), inject a pointer to re-orient from the KB")
    parser.add_argument("--max-age", type=float, default=7200, help="seconds after which a note is stale")
    parser.add_argument("--startup-max-age", type=float, default=900,
                        help="seconds after which a new conversation (source startup) no longer takes the note")
    parser.add_argument("--log", type=Path, help="append one JSON line per event (no content)")
    parser.add_argument("--client", default="claude", help="the client running the hook (see clients.py)")
    parser.add_argument("--link-wait", type=float, default=3,
                        help="seconds a /clear waits for the package its SessionEnd is saving")
    parser.add_argument("--process", help=argparse.SUPPRESS)  # tests: the client process, instead of looking it up
    args = parser.parse_args()
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        clients, resume = load("clients"), load("resume")
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        entry.update(client=args.client, fields=sorted(event.keys()) if isinstance(event, dict) else None)
        why = clients.foreign(args.client, event)
        if why:
            entry["decision"] = why
            return
        info = clients.normalized(args.client, event)
        source, cwd, transcript, session = info["source"], info["cwd"], info["transcript"], info["session"]
        entry.update(event=event.get("hook_event_name"), source=source, session=session, cwd=cwd)
        store = resume.Store(clients, args.handoff, args.held, args.packages)
        store.prune()
        linkable = args.client in clients.LINKED and args.packages is not None
        checkpointed = args.client in clients.CHECKPOINT and args.packages is not None
        name = event.get("hook_event_name")
        if name in ("SessionEnd", "Stop"):
            # SessionEnd: the conversation that /clear ends (Claude Code). Stop: the end of a turn, a checkpoint on
            # clients with no such exit event. Either way, save this conversation's package.
            entry["reason"] = event.get("reason")
            if (name == "SessionEnd" and (event.get("reason") != "clear" or not linkable)) or (
                    name == "Stop" and not checkpointed):
                entry["decision"] = "end-not-handled"
            else:
                began, process = time.time(), args.process or clients.client_process()
                saved = store.save(cwd, session, transcript, args.client, process, args.snapshot_chars)
                entry.update(decision=saved if name == "SessionEnd" else "checkpoint-" + saved, process=process,
                             seconds=round(time.time() - began, 2))
            return
        base, startup = args.handoff, source == "startup"
        claude_style = args.client in clients.CLAUDE_STYLE
        # Claude Code, Codex and Droid always name the transcript: a startup payload without one is another client's.
        evidence = bool(transcript) or not claude_style
        if args.client in clients.OPENCODE_FAMILY and startup and transcript and clients.opencode_has_messages(
                transcript, session):
            startup, source = False, "resume"
        window = args.startup_max_age if startup else args.max_age
        usable = evidence or not startup
        items = store.gather(cwd, window) if usable else {}
        # A new conversation never takes a snapshot: only notes and held messages, as before 0.3.0. On OpenCode and
        # Kilo a new session (/new) is the restart itself, so it does, within the same short window.
        if startup and args.client not in clients.OPENCODE_FAMILY:
            items = {k: {p: v[p] for p in ("note", "held") if v.get(p)} for k, v in items.items()
                     if v.get("note") or v.get("held")}
        if fresh(base, args.max_age):  # the one note every project read before 0.2.1: never delivered
            entry["legacy_note"] = "ignored"
        restart = "the restart" if startup else "/clear"
        chosen, ask_first, why_list = None, False, None
        if source == "compact" and args.compact:
            context = compact_pointer(args.kb_root)
            sys.stdout.write(json.dumps(clients.session_output(args.client, context), ensure_ascii=False))
            entry.update(decision="pointer", chars=len(context))
            return
        if source not in args.sources.split(","):
            entry["decision"] = "source-not-handled"
            return
        if source == "clear" and linkable:
            process = args.process or clients.client_process()
            found, began = store.linked(process, window), time.time()
            # The SessionEnd hook may still be writing the package: wait for it a little, never long.
            while found is None and process and time.time() - began < args.link_wait:
                time.sleep(0.1)
                found = store.linked(process, window)
            if found is not None:  # this conversation's package, even if saved under a folder it had moved to
                chosen, items = found[0], {**items, found[0]: found[1]}
            entry.update(process=process, linked=chosen is not None, waited=round(time.time() - began, 2))
            if chosen is None and items:
                why_list = ("This /clear could not be matched to the conversation it ended, and this working directory "
                            "has restarts left by conversations that may still be open.")
        else:
            if checkpointed and (source == "clear" or args.client in clients.OPENCODE_FAMILY):
                # Checkpoint clients: this restart's own package is one saved from the same client process. That
                # process can run several chats (a VS Code window, a server), so it narrows, it does not prove.
                # Checkpoints of other processes belong to chats still open elsewhere: never offered.
                process = args.process or clients.client_process()
                own = store.by_process(items, process, session)
                entry.update(process=process, same_process=len(own))
                items = ({own[0]: items[own[0]]} if len(own) == 1 else
                         {k: v for k, v in items.items() if k in own or v.get("note") or v.get("held")})
            if len(items) == 1:
                chosen = next(iter(items))
                ask_first = source == "clear" and bool(items[chosen].get("held"))  # not proven: shown first
            elif items:
                why_list = ("Before " + restart + ", different conversations in this working directory each left a "
                            "restart for mem-optimize to carry over.")
        if why_list:
            context = resume.choices(store, items, cwd, restart, why_list)
            notice = "MEM: several restarts were left in this folder; choose which one to resume."
            sys.stdout.write(json.dumps(clients.session_output(args.client, context, notice), ensure_ascii=False))
            entry.update(decision="ambiguous", chars=len(context), packages=len(items))
            return
        if chosen is None:
            elsewhere = any(fresh(h, window) for h in clients.held_files(args.held))
            entry["decision"] = ("no-transcript" if not usable else "other-project" if elsewhere else
                                 "legacy-note-ignored" if entry.get("legacy_note") else
                                 "stale-handoff" if clients.project_notes(base, cwd) else "no-handoff")
            return
        item = items[chosen]
        only_snapshot = not item.get("note") and not item.get("held")
        if only_snapshot and args.restore == "off":
            entry["decision"] = "restore-off"
            return
        if only_snapshot and args.restore == "offer":
            context = resume.offer(store, item, cwd, chosen)
            sys.stdout.write(json.dumps(clients.session_output(args.client, context), ensure_ascii=False))
            entry.update(decision="offered", chars=len(context))
            return
        context, notice, plan = resume.compose(item, restart, startup, claude_style, args.kb_root,
                                               ask_first=ask_first, snapshot=args.restore == "auto")
        # Delivered before printing: if another session took it meanwhile, nothing is printed.
        if not resume.deliver(item, plan):
            entry["decision"] = "taken"
            return
        sys.stdout.write(json.dumps(clients.session_output(args.client, context, notice), ensure_ascii=False))
        entry.update(decision="injected", chars=len(context), note=bool(item.get("note")),
                     held=bool(item.get("held")), snapshot=bool(item.get("package")),
                     inline=plan["note_inline"] and plan["held_inline"])
    except Exception as error:  # never break a session start
        entry["decision"] = "error: " + type(error).__name__
    finally:
        log(args.log, entry)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
