"""Resume packages: what one conversation leaves for the session that continues it, and the claim command.

A package is keyed by folder and session and gathers up to three things: the snapshot of the conversation's last
exchanges, saved when it ended with /clear (Claude Code's SessionEnd; <packages>/<folder 12 hex>-<session 8>.json,
with the client process it ran in); the handoff note it wrote (handoff-<folder 12>-<session 8>.md beside --handoff);
and the message the advisor held back (held-prompt-<session 16>.json beside --held, which records its session and
folder). hook_session.py restores one package after /clear, or lists several; the agent claims a listed one with:

  resume.py claim ID --cwd DIR --handoff FILE --held FILE --packages DIR

which prints the package whole and marks it delivered, once: a second claim, from another chat, finds nothing.
Delivered parts are renamed (.consumed-<stamp>, .delivered-<stamp>) and deleted after a week, so a package is never
lost before then. Standard library only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

CAP = 9800  # the whole injected context, below the 10,000-character additionalContext cap
LIMIT = 9000  # a note longer than this always goes by path
KEEP = 7 * 86400  # delivered parts and unclaimed packages are deleted after a week
LINK = 60  # seconds within which a SessionEnd and a SessionStart can be one /clear (measured: under 1 s)


def load(name):
    spec = importlib.util.spec_from_file_location("mem_optimize_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, AttributeError):
        return {}
    return found if isinstance(found, dict) else {}


def fresh(path, max_age, now=None):
    try:
        return (now or time.time()) - path.stat().st_mtime <= max_age
    except OSError:
        return False


CLAIM_STALE = 60  # seconds after which a .claim marker is a leftover of an interrupted delivery


def reserved(path):
    """Whether a part is being delivered by another session right now: its .claim marker exists and is recent. An
    older marker is a leftover of an interrupted delivery, which reserve() clears: the part is a candidate again."""
    return fresh(Path(str(path) + ".claim"), CLAIM_STALE)


def reserve(path):
    """Take a part for delivery: create its .claim marker exclusively. A marker left by a crash goes after a minute."""
    marker = Path(str(path) + ".claim")
    for _ in range(2):
        try:
            os.close(os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return marker
        except FileExistsError:
            if fresh(marker, CLAIM_STALE):
                return None
            marker.unlink(missing_ok=True)
        except OSError:
            return None
    return None


def hhmm(seconds):
    return time.strftime("%H:%M", time.localtime(seconds))


def renamed(path, label):
    """A free name for a delivered part: <stem>.<label>-<stamp><suffix>, numbered if taken this second."""
    stamp, number = path.stem + "." + label + "-" + time.strftime("%Y%m%d-%H%M%S"), 1
    target = path.with_name(stamp + path.suffix)
    while target.exists():
        number += 1
        target = path.with_name("%s-%d%s" % (stamp, number, path.suffix))
    return target


def last_writes(transcript, scan=1 << 22):
    """[(path, content)] of the files the main conversation last wrote or edited, oldest first, from the last 4 MB
    of a Claude Code transcript: content is what the Write tool wrote, None for an edit."""
    with open(transcript, "rb") as stream:
        stream.seek(0, 2)
        start = max(0, stream.tell() - scan)
        stream.seek(start)
        lines = stream.read().split(b"\n")[1 if start else 0:]
    writes = {}
    for line in lines:
        if b'"tool_use"' not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("type") != "assistant" or record.get("isSidechain"):
            continue
        for block in (record.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            given = block.get("input") or {}
            if block.get("name") in ("Write", "Edit", "MultiEdit") and given.get("file_path"):
                path = Path(given["file_path"])
                writes.pop(str(path), None)  # keep the order of the last write
                writes[str(path)] = (path, given.get("content") if block["name"] == "Write" else None)
    return list(writes.values())


class Store:
    """Where one hook installation keeps notes, held messages and packages."""

    def __init__(self, clients, handoff=None, held=None, packages=None):
        self.clients, self.handoff, self.held, self.packages = clients, handoff, held, packages

    def prefix(self, cwd):
        return self.clients.digest(self.clients.folder(cwd), 12)

    def package(self, cwd, session):
        return self.packages / (self.prefix(cwd) + "-" + self.clients.digest(session, 8) + ".json")

    def gather(self, cwd, window, now=None):
        """{key: {"note", "held", "package": path}} of what this folder's conversations left within window. The key is
        the session's 8 hex digits ("folder" for 0.2.0's one note per folder)."""
        clients, items, now = self.clients, {}, now or time.time()
        if not cwd:
            return items
        start = len(self.handoff.stem) + 13 if self.handoff is not None else 0
        for note in clients.project_notes(self.handoff, cwd):
            if fresh(note, window, now):
                items.setdefault(note.stem[start + 1:] or "folder", {})["note"] = note
        for held in clients.held_files(self.held):
            kept = read(held)
            if fresh(held, window, now) and kept.get("cwd") and clients.folder(kept["cwd"]) == clients.folder(cwd):
                key = clients.digest(kept["session"], 8) if kept.get("session") else "held-" + held.stem[-6:]
                items.setdefault(key, {})["held"] = held
        if self.packages is not None and self.packages.is_dir():
            prefix = self.prefix(cwd) + "-"
            for package in self.packages.glob(prefix + "*.json"):
                if ".delivered-" not in package.name and fresh(package, window, now):
                    items.setdefault(package.stem[len(prefix):], {})["package"] = package
        # a package another session is delivering right now is no candidate, whichever part it holds
        return {key: item for key, item in items.items() if not any(reserved(part) for part in item.values())}

    def prune(self, now=None):
        """Delete delivered parts and unclaimed packages older than KEEP."""
        now = now or time.time()
        found = []
        if self.packages is not None and self.packages.is_dir():
            found += list(self.packages.glob("*.json"))
        if self.held is not None and self.held.parent.is_dir():
            found += list(self.held.parent.glob(self.held.stem + "*.consumed-*" + self.held.suffix))
        for path in found:
            try:
                if now - path.stat().st_mtime >= KEEP:
                    path.unlink()
            except OSError:
                pass

    def save(self, cwd, session, transcript, client, process, snapshot_chars=6000, now=None):
        """At a /clear's SessionEnd (Claude Code), or at the end of a turn on the other clients: the snapshot of the
        conversation's last exchanges, its client process, and (Claude Code) the handoff note it wrote, adopted under
        its session's name. Returns what was saved."""
        clients = self.clients
        if not cwd or not session or self.packages is None:
            return "no-session"
        prompt = load("hook_prompt")
        if client in clients.OPENCODE_FAMILY:  # the session lives in the client's database
            found = clients.opencode_turns(transcript, session) if transcript else []
        else:
            found = prompt.turns(Path(transcript)) if transcript and Path(transcript).is_file() else []
        adopted = self.adopt(cwd, session, transcript) if client in clients.LINKED else False
        record = {"session": session, "cwd": cwd, "client": client, "process": process, "ended": now or time.time(),
                  "snapshot": prompt.snapshot(found, snapshot_chars) if snapshot_chars > 0 else ""}
        target = self.package(cwd, session)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name("%s.%d.%s.tmp" % (target.stem, os.getpid(), os.urandom(4).hex()))
        temporary.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, target)
        return "saved" + ("+note" if adopted else "")

    def adopt(self, cwd, session, transcript):
        """A handoff note this conversation wrote under another name (from note-path, guessed, or the shared
        handoff.md) becomes its session's, only on proof that the file still holds what this conversation wrote: the
        Write tool's content in its transcript. Having written a path once proves nothing about its content now
        (another session may have overwritten it since); an edited note has no such proof and stays where it is."""
        clients = self.clients
        if self.handoff is None or not transcript or not Path(transcript).is_file():
            return False
        target = clients.project_note(self.handoff, cwd, session)
        series = self.handoff.stem + "-" + self.prefix(cwd)
        for path, content in reversed(last_writes(Path(transcript))):
            if (clients.folder(str(path.parent)) != clients.folder(str(self.handoff.parent)) or not path.is_file()
                    or not (path.name == self.handoff.name or (path.name.startswith(series)
                                                               and ".consumed-" not in path.name))):
                continue
            if clients.folder(str(path)) == clients.folder(str(target)):
                return True  # the advisor named it after this session: nobody else writes it
            try:
                proven = content is not None and path.read_text(encoding="utf-8") == content
            except OSError:
                proven = False
            if proven and not target.exists():
                os.replace(path, target)
            return target.exists()
        return False

    def by_process(self, items, process, session):
        """The keys of this folder's packages saved from the same client process by another session (checkpoint
        clients: a window's or a server's process may run several chats)."""
        return [key for key, item in items.items() if item.get("package")
                and read(item["package"]).get("process") == process and read(item["package"]).get("session") != session]

    def linked(self, process, window, now=None):
        """The package this /clear continues: ended moments ago in the same client process, whatever folder it was
        saved under (a chat's working directory can move during the conversation: measured 2026-10-29). Returns
        (key, item) with the note and held message of the same conversation, or None."""
        now, best = now or time.time(), None
        if not process or self.packages is None or not self.packages.is_dir():
            return None
        for package in self.packages.glob("*.json"):
            record = read(package) if ".delivered-" not in package.name and not reserved(package) else {}
            if record.get("process") == process and 0 <= now - (record.get("ended") or 0) <= LINK:
                if best is None or record["ended"] > best[1]["ended"]:
                    best = (package, record)
        if best is None:
            return None
        package, record = best
        key = package.stem.split("-", 1)[1]
        item = self.gather(record["cwd"], window, now).get(key) or {}
        return key, {**item, "package": package}


def compose(item, restart="/clear", startup=False, claude_style=True, kb_root=None, cap=CAP, ask_first=False,
            snapshot=True):
    """The context carrying one package over. The held message always arrives whole, inline or by the path it will
    be renamed to; the note inline or by path; the snapshot in what room is left. With cap None, everything inline.
    Returns (context, notice, plan): plan names the renames that mark it delivered."""
    note, held, package = item.get("note"), item.get("held"), item.get("package")
    kept, record = read(held) if held else {}, read(package) if package else {}
    prompt = kept.get("prompt") or ""
    recent = ((record.get("snapshot") or kept.get("snapshot") or "").strip()) if snapshot else ""
    ended = record.get("ended") or (held.stat().st_mtime if held else None)
    text = note.read_text(encoding="utf-8") if note else ""
    plan = {"note": note and renamed(note, "consumed"), "held": held and renamed(held, "consumed"),
            "package": package and renamed(package, "delivered")}
    orient = (" If this workspace has a MEM knowledge base, re-orient from it first: read its MEM.index.md and the "
              "resume point of the latest log." if kb_root is None else
              " Re-orient from the KB first: read " + str(Path(kb_root) / "MEM.index.md") +
              " and the resume point of the latest log.")
    combos = ((True, True),) if cap is None else ((True, True), (False, True), (True, False), (False, False))
    for note_inline, held_inline in combos:
        if note_inline and cap is not None and len(text) > LIMIT:
            continue
        parts, confirm = [], []
        if note:
            opened = ("" if not startup else
                      " The user opened a new conversation instead of typing /clear: if the note is about another "
                      "project than this session's working directory, ignore it and say so." if claude_style else
                      " This is a new conversation: if the note is about another project than this session's "
                      "working directory, ignore it and say so.")
            body = text if note_inline else ("A handoff note from the previous session is too long to inline; read it "
                                             "first: " + str(plan["note"].resolve()))
            parts.append("Resuming from the previous session's handoff note (written before " + restart + " at the "
                         "user's confirmation). Continue from it; do not ask the user to repeat it." + opened + "\n\n" +
                         body)
            confirm.append("the handoff note written at " + hhmm(note.stat().st_mtime) + " was restored")
        if held:
            message = ("\n\n<<<\n" + prompt + "\n>>>" if held_inline else
                       " The message is too long to inline: read it whole first, the \"prompt\" field of " +
                       str(plan["held"].resolve()) + ".")
            act = (" It was matched to this conversation by its folder only: show it to the user and ask whether to "
                   "act on it before doing anything." if ask_first else
                   " Treat the message as the user's request and act on it at the user's next input, unless that input "
                   "clearly asks for something else (then follow the new input).")
            parts.append("Before " + restart + ", mem-optimize held back the user's message so that it would not "
                         "re-send the previous session's whole context." + ("" if note else orient) + act + message)
            confirm.append("their held message was carried over")
        if recent:
            # where the whole snapshot stays once delivered: the package, or the held message it came with
            source = plan["package"] if record.get("snapshot") else plan["held"]
            whole = (" They were cut to fit: read them whole in the \"snapshot\" field of " + str(source.resolve()) +
                     ".")
            room = None if cap is None else cap - sum(len(p) + 2 for p in parts) - 400 - len(whole)
            if room is not None and room <= 500:  # no room: by path only
                parts.append("The previous session's last exchanges did not fit here: read them in the \"snapshot\" "
                             "field of " + str(source.resolve()) + " before answering.")
                confirm.append("the last exchanges were restored by path")
            else:
                if room is not None and len(recent) > room:  # keep the latest turns, and say where the rest is
                    recent_cut = recent[-room:]
                    recent_cut = (recent_cut[recent_cut.find("\n\nUser: ") + 2:] if "\n\nUser: " in recent_cut
                                  else recent_cut)
                else:
                    recent_cut, whole = recent, ""
                when = (" (the session that ended at " + hhmm(ended) + ")") if ended else ""
                parts.append("The previous session's last exchanges" + when + ", extracted mechanically from its "
                             "transcript (oldest first; the KB stays authoritative where they differ)." +
                             ("" if note or held else orient) + " Use them to follow the user's next messages; if the "
                             "user starts something else, follow the user." + whole + "\n\n" + recent_cut)
                confirm.append("the last exchanges" + (" of the " + hhmm(ended) + " session" if ended else "") +
                               " were restored")
        # The VS Code extension does not display systemMessage: the agent's first reply is the visible confirmation.
        context = "\n\n".join(parts) + ("\n\nOpen your first reply with one short line telling the user that " +
                                       " and ".join(confirm) + ".")
        if cap is None or len(context) <= cap:
            break
    plan.update(note_inline=note_inline, held_inline=held_inline)
    return context, "MEM: " + " and ".join(confirm) + ".", plan


def deliver(item, plan):
    """Mark a package delivered before its context is printed, all or nothing: every part is reserved first (an
    exclusive .claim marker, in a fixed order), then checked, then renamed. False when another session holds or took
    any part: nothing is renamed and nothing is printed then."""
    parts = sorted((part for part in ("package", "note", "held") if item.get(part)), key=lambda part: str(item[part]))
    markers = []
    try:
        for part in parts:
            marker = reserve(item[part])
            if marker is None:
                return False
            markers.append(marker)
        if not all(item[part].is_file() for part in parts):
            return False
        for part in parts:
            os.rename(item[part], plan[part])
        return True
    finally:
        for marker in markers:
            marker.unlink(missing_ok=True)


def claim_command(store, cwd):
    runner = Path(__file__).resolve()
    parts = ['"%s"' % Path(sys.executable).as_posix(), "-I", "-B", '"%s"' % runner.as_posix(), "claim", "<id>",
             "--cwd", '"%s"' % cwd]
    for flag, value in (("--handoff", store.handoff), ("--held", store.held), ("--packages", store.packages)):
        if value is not None:
            parts += [flag, '"%s"' % Path(value).as_posix()]
    return " ".join(parts)


def summary(item):
    """One line on what a package holds: the note's first line, the held message's start, the snapshot."""
    bits, times = [], []
    if item.get("note"):
        try:
            first = next((line.strip("# ").strip() for line in item["note"].read_text(encoding="utf-8").splitlines()
                          if line.strip()), "")
        except OSError:
            first = ""
        bits.append("handoff note: " + first[:120])
        times.append(item["note"].stat().st_mtime)
    if item.get("held"):
        prompt = " ".join((read(item["held"]).get("prompt") or "").split())
        bits.append("held message: \"" + prompt[:160] + ("…" if len(prompt) > 160 else "") + "\"")
        times.append(item["held"].stat().st_mtime)
    if item.get("package"):
        record = read(item["package"])
        last = next((line[6:] for line in reversed((record.get("snapshot") or "").splitlines())
                     if line.startswith("User: ")), "")
        bits.append("last exchanges" + (", last request: \"" + last[:120] + "\"" if last else ""))
        times.append(record.get("ended") or item["package"].stat().st_mtime)
    return max(times) if times else 0, "; ".join(bits)


def choices(store, items, cwd, restart, why):
    """A short list of the packages left in this folder, for the user to pick one; nothing is consumed."""
    lines = []
    for key, item in sorted(items.items(), key=lambda pair: -summary(pair[1])[0]):
        at, what = summary(item)
        lines.append("- id %s, %s: %s" % (key, hhmm(at) if at else "?", what))
    head = (why + " Open your first reply by showing the user this list and asking which one to resume; act on none "
            "of them until the user answers. Then load only the chosen one by running this command with its id: it "
            "prints the package whole and marks it delivered, so that no other conversation takes it.\n\n" +
            claim_command(store, cwd) + "\n\n")
    return (head + "\n".join(lines))[:CAP]


def offer(store, item, cwd, key):
    at, _ = summary(item)
    return ("The previous session in this chat (ended at " + hhmm(at) + ") left a snapshot of its last exchanges, not "
            "restored (the user chose to be asked). Tell the user in one short line that it can be restored; if they "
            "want it, run:\n\n" + claim_command(store, cwd).replace("<id>", key))


def claim(store, key, cwd):
    """Print one package whole and mark it delivered; exit 1 when it is gone (claimed already, or expired)."""
    items = store.gather(cwd, KEEP)
    item = items.get(key)
    if not item:
        sys.stdout.write("mem-optimize: no package %s in %s (claimed already by another conversation, or expired).\n"
                         % (key, cwd))
        return 1
    context, _, plan = compose(item, cap=None)
    if not deliver(item, plan):
        sys.stdout.write("mem-optimize: package %s was just claimed by another conversation.\n" % key)
        return 1
    sys.stdout.write(context.replace("Open your first reply with one short line telling the user that",
                                     "Tell the user in one short line that") + "\n")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("claim",))
    parser.add_argument("id")
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--handoff", type=Path)
    parser.add_argument("--held", type=Path)
    parser.add_argument("--packages", type=Path)
    args = parser.parse_args()
    store = Store(load("clients"), args.handoff, args.held, args.packages)
    sys.exit(claim(store, args.id, args.cwd))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
