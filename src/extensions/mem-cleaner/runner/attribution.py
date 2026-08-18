"""Which files this agent wrote, and whether they are still as it left them.

Attribution comes from the operation that changed a file, never from style,
heuristics or working-tree state. In particular **never from `git diff`**: that
reports everything uncommitted, including work the user did before the session
began, and using it would widen automatic rewriting from "what this agent
produced" to "everything currently dirty".

The record is `path` + `expected_hash`, captured immediately after the agent's
last write to each file. It lives in per-host transient state -- paths and
hashes only, never content -- and is namespaced by session, so two agents on
one host never share a set.

A hash that no longer matches means a human edited the file since. That file is
**skipped**, not cleaned: a human's edit is not the agent's output to work on.
"""

from __future__ import annotations

import fnmatch
import json
import os

from . import state


ELIGIBLE = "eligible"
CHANGED = "changed since recorded"
MISSING = "no longer exists"
EXCLUDED = "excluded by configuration"
NOT_INCLUDED = "not matched by extensions_cleaner_include"


class Entry:
    def __init__(self, path, expected_hash):
        self.path = path
        self.expected_hash = expected_hash

    def status(self):
        current = state.hash_file(self.path)
        if current is None:
            return MISSING
        if current != self.expected_hash:
            return CHANGED
        return ELIGIBLE


class Record:
    """One session's set of written files."""

    def __init__(self, kb_root, session):
        self.kb_root = kb_root
        self.session = session
        self.entries = {}
        self._path = os.path.join(state.for_kb(kb_root), "session-%s.json" % session)
        self._load()

    def _load(self):
        if not os.path.isfile(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (ValueError, OSError):
            # A record that cannot be read is treated as absent rather than
            # repaired. Re-recording is cheap; guessing at half of it is not.
            return
        for item in data.get("entries", []):
            self.entries[item["path"]] = Entry(item["path"], item["expected_hash"])

    def save(self):
        payload = {
            "version": 1,
            "session": self.session,
            "kb_root": os.path.abspath(self.kb_root),
            "entries": [
                {"path": e.path, "expected_hash": e.expected_hash}
                for e in sorted(self.entries.values(), key=lambda e: e.path)
            ],
        }
        temporary = self._path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(temporary, self._path)

    def add(self, path):
        """Record a file as written by the agent, at its current content."""
        absolute = os.path.abspath(path)
        digest = state.hash_file(absolute)
        if digest is None:
            raise ValueError("%s: does not exist" % path)
        # Re-recording replaces the hash: the agent wrote it again, so the
        # baseline is the new content, not the first one.
        self.entries[absolute] = Entry(absolute, digest)
        return self.entries[absolute]

    def forget(self):
        self.entries = {}
        if os.path.isfile(self._path):
            os.remove(self._path)

    def __len__(self):
        return len(self.entries)


def sessions(kb_root):
    """Session ids with a record on this host."""
    directory = state.for_kb(kb_root)
    found = []
    for name in sorted(os.listdir(directory)):
        if name.startswith("session-") and name.endswith(".json"):
            found.append(name[len("session-") : -len(".json")])
    return found


def select(record, cfg):
    """Split a record into (eligible, skipped).

    `skipped` is a list of (path, reason). Every exclusion is reported: a file
    silently dropped from an automatic run is indistinguishable from one that
    was cleaned successfully.
    """
    eligible = []
    skipped = []
    for entry in sorted(record.entries.values(), key=lambda e: e.path):
        reason = _configuration_reason(entry.path, cfg)
        if reason is not None:
            skipped.append((entry.path, reason))
            continue
        status = entry.status()
        if status is ELIGIBLE:
            eligible.append(entry)
        else:
            skipped.append((entry.path, status))
    return eligible, skipped


def _configuration_reason(path, cfg):
    relative = relative_to(path, cfg.project_root)
    if cfg.exclude and _any_match(relative, cfg.exclude):
        return EXCLUDED
    if cfg.include and not _any_match(relative, cfg.include):
        return NOT_INCLUDED
    return None


def relative_to(path, root):
    """Path relative to a root, with forward slashes; absolute if outside it."""
    try:
        relative = os.path.relpath(path, root)
    except ValueError:
        return path.replace("\\", "/")
    if relative.startswith(".."):
        return path.replace("\\", "/")
    return relative.replace("\\", "/")


def _any_match(relative, patterns):
    return any(_matches(relative, pattern) for pattern in patterns)


def _matches(relative, pattern):
    """Glob match, with one documented accommodation for `**/`.

    `fnmatch` has no `**`: its `*` already crosses separators, so `**/*.py`
    matches `src/a/b.py` but not a top-level `b.py`, which is not what anyone
    writing that pattern means. So a leading `**/` is also tried stripped.
    Everything else is plain `fnmatch`, and the limitation is stated rather
    than papered over.
    """
    if fnmatch.fnmatch(relative, pattern):
        return True
    if pattern.startswith("**/") and fnmatch.fnmatch(relative, pattern[3:]):
        return True
    return False
