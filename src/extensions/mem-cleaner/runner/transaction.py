"""Journalled, recoverable file replacement.

Option B of the three considered: candidates are installed at their real paths,
because a test suite has to see them there, and a journal makes the batch
recoverable. Per file the replacement is atomic; the batch is *recoverable, not
atomic*, and that is stated rather than implied.

    prepared --> installed --> validating --> committed
                     |
                     +--> rolling-back --> restored

The commit point is after validation, not after the last write. Clearing the
journal once every file is in place would discard the ability to roll back at
exactly the moment rollback becomes likely.

Two compare-and-swaps, for two different reasons:

  * before installing, the original must still be the file we measured. If it
    changed, someone edited it while we worked, and their edit is not ours to
    overwrite.
  * before restoring, the file must still be the candidate we installed. If it
    changed, someone edited it after the crash, and finishing an old rollback
    would destroy newer work.
"""

from __future__ import annotations

import json
import os
import shutil

from . import state


JOURNAL_VERSION = 1

PREPARED = "prepared"
INSTALLED = "installed"
VALIDATING = "validating"
COMMITTED = "committed"
ROLLING_BACK = "rolling-back"
RESTORED = "restored"


class TransactionError(RuntimeError):
    """The transaction cannot proceed and the caller must stop."""


class ConflictError(TransactionError):
    """A file changed underneath us. Never resolved automatically."""


class Entry:
    def __init__(
        self,
        path,
        original_hash,
        backup=None,
        candidate_hash=None,
        installed=False,
        intended=False,
    ):
        self.path = path
        self.original_hash = original_hash
        self.backup = backup
        self.candidate_hash = candidate_hash
        # `intended` is written to disk *before* the replace, `installed`
        # *after*. A crash between them leaves intended=True, installed=False,
        # which is the only state that needs the file itself consulted -- see
        # resolve().
        self.intended = intended
        self.installed = installed

    def to_dict(self):
        return {
            "path": self.path,
            "original_hash": self.original_hash,
            "backup": self.backup,
            "candidate_hash": self.candidate_hash,
            "intended": self.intended,
            "installed": self.installed,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            data["path"],
            data["original_hash"],
            data.get("backup"),
            data.get("candidate_hash"),
            data.get("installed", False),
            data.get("intended", data.get("installed", False)),
        )

    def resolve(self):
        """Is this entry's candidate actually on disk?

        Returns 'installed', 'not-installed' or 'indeterminate'. Only the
        interrupted case reaches the disk: a confirmed record is trusted, and
        an entry that never got as far as intent cannot have been written.
        """
        if self.installed:
            return "installed"
        if not self.intended:
            return "not-installed"
        current = state.hash_file(self.path)
        if current is None:
            return "indeterminate"
        if self.candidate_hash and current == self.candidate_hash:
            return "installed"
        if current == self.original_hash:
            return "not-installed"
        return "indeterminate"


class Transaction:
    """One run over one set of files."""

    def __init__(self, kb_root, session, pipeline_id):
        self.kb_root = kb_root
        self.session = session
        self.pipeline_id = pipeline_id
        self.state = PREPARED
        self.entries = []
        self._dir = state.for_kb(kb_root)
        self._path = os.path.join(self._dir, "journal-%s.json" % session)
        self._backups = os.path.join(self._dir, "backup-%s" % session)

    # -- lifecycle ---------------------------------------------------------

    def prepare(self, targets):
        """Record originals and back them up. Nothing is modified yet.

        `targets` is a sequence of (path, expected_hash). An expected_hash of
        None means "no expectation", which is only correct for a target the
        user named explicitly.
        """
        os.makedirs(self._backups, exist_ok=True)
        for index, (path, expected) in enumerate(targets):
            current = state.hash_file(path)
            if current is None:
                raise TransactionError("%s: does not exist" % path)
            if expected is not None and current != expected:
                raise ConflictError(
                    "%s: changed since it was recorded; skipping is correct, "
                    "overwriting is not" % path
                )
            backup = os.path.join(self._backups, "%04d-%s" % (index, os.path.basename(path)))
            shutil.copy2(path, backup)
            self.entries.append(Entry(path, current, backup))
        self.state = PREPARED
        self._write()
        return self

    def install(self, candidates):
        """Replace originals with candidates, atomically, one file at a time.

        `candidates` maps path -> candidate file path. A path missing from it
        is left alone, which is how a stage that changed nothing is expressed.
        """
        self.state = INSTALLED
        self._write()
        for entry in self.entries:
            candidate = candidates.get(entry.path)
            if candidate is None:
                continue
            # The original must still be what we measured in prepare().
            current = state.hash_file(entry.path)
            if current != entry.original_hash:
                raise ConflictError(
                    "%s: changed while the pipeline was running" % entry.path
                )

            # Record the *intention* durably before touching the file. A crash
            # between the replace and the confirmation used to leave a journal
            # saying "not installed" over a file that had been installed --
            # recovery then discarded the backup and the rollback became
            # impossible. Writing intent first makes that window recoverable:
            # the candidate hash on disk identifies what happened.
            entry.candidate_hash = state.hash_file(candidate)
            entry.intended = True
            self._write()

            os.replace(candidate, entry.path)

            entry.installed = True
            self._write()
        return self

    def validating(self):
        self.state = VALIDATING
        self._write()
        return self

    def commit(self):
        """Accept the installed files and discard the backups."""
        self.state = COMMITTED
        self._write()
        self._discard()
        return self

    def rollback(self, reason=""):
        """Put every installed file back, refusing where it changed since."""
        self.state = ROLLING_BACK
        self.reason = reason
        self._write()
        conflicts = restore_entries(self.entries, persist=self._write)
        if conflicts:
            # The journal stays on disk: a partial rollback is exactly the
            # situation someone has to look at.
            self._write()
            return conflicts
        self.state = RESTORED
        self._write()
        self._discard()
        return []

    # -- persistence -------------------------------------------------------

    def _write(self):
        payload = {
            "version": JOURNAL_VERSION,
            "kb_root": os.path.abspath(self.kb_root),
            "session": self.session,
            "pipeline": self.pipeline_id,
            "state": self.state,
            "entries": [e.to_dict() for e in self.entries],
        }
        temporary = self._path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self._path)

    def _discard(self):
        shutil.rmtree(self._backups, ignore_errors=True)
        if os.path.isfile(self._path):
            os.remove(self._path)


def restore_entries(entries, persist=None):
    """Restore installed entries. Returns the paths it refused to touch.

    `persist` is called after each file so that a crash during the rollback
    leaves a journal that reflects what has already been undone.
    """
    conflicts = []
    for entry in entries:
        if not entry.backup:
            continue

        status = entry.resolve()
        if status == "not-installed":
            continue
        if status == "indeterminate":
            conflicts.append(
                "%s: interrupted mid-install and the file matches neither the "
                "original nor the candidate; not touched" % entry.path
            )
            continue

        if not os.path.isfile(entry.backup):
            conflicts.append("%s: backup is missing" % entry.path)
            continue

        current = state.hash_file(entry.path)
        if current is not None and current != entry.candidate_hash:
            # Someone edited the file after we installed our candidate.
            # Finishing this rollback would destroy their work.
            conflicts.append(
                "%s: edited since the pipeline installed its candidate; "
                "not restored" % entry.path
            )
            continue

        _atomic_restore(entry.backup, entry.path)
        entry.installed = False
        entry.intended = False
        if persist is not None:
            persist()
    return conflicts


def _atomic_restore(backup, path):
    """Put a backup back in place without ever leaving a partial file.

    A plain copy writes into the target: a crash halfway leaves a file that is
    neither the original nor the candidate, which is the one state recovery
    cannot reason about.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    temporary = os.path.join(directory, ".mem-cleaner-restore-%s" % os.path.basename(path))
    shutil.copy2(backup, temporary)
    os.replace(temporary, path)


# -- recovery --------------------------------------------------------------


class Recovered:
    def __init__(self, path, journal, action, conflicts):
        self.path = path
        self.journal = journal
        self.action = action
        self.conflicts = conflicts


def pending(kb_root):
    """Journals left behind by an interrupted run."""
    directory = state.for_kb(kb_root)
    found = []
    for name in sorted(os.listdir(directory)):
        if not (name.startswith("journal-") and name.endswith(".json")):
            continue
        path = os.path.join(directory, name)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                found.append((path, json.load(handle)))
        except (ValueError, OSError) as error:
            found.append((path, {"state": "unreadable", "error": str(error)}))
    return found


def recover(kb_root):
    """Resolve every pending journal. Runs before anything else."""
    results = []
    for path, journal in pending(kb_root):
        recorded = journal.get("state")

        if recorded == "unreadable":
            results.append(Recovered(path, journal, "left in place", [journal.get("error", "")]))
            continue

        if recorded in (COMMITTED, RESTORED):
            # Finished, and the discard did not complete. Safe to clean up.
            _cleanup(path, journal)
            results.append(Recovered(path, journal, "cleaned up", []))
            continue

        entries = [Entry.from_dict(e) for e in journal.get("entries", [])]

        if recorded == PREPARED and not any(e.intended for e in entries):
            # Intent is recorded before the replace, so with none recorded the
            # file cannot have been touched.
            _cleanup(path, journal)
            results.append(Recovered(path, journal, "discarded (nothing installed)", []))
            continue

        def persist(journal_path=path, journal_data=journal, entry_list=entries):
            journal_data["entries"] = [e.to_dict() for e in entry_list]
            temporary = journal_path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(journal_data, handle, indent=2)
            os.replace(temporary, journal_path)

        conflicts = restore_entries(entries, persist=persist)
        if conflicts:
            persist()
            results.append(Recovered(path, journal, "partially restored", conflicts))
            continue
        _cleanup(path, journal)
        results.append(Recovered(path, journal, "rolled back", []))
    return results


def _cleanup(journal_path, journal):
    session = journal.get("session")
    if session:
        shutil.rmtree(
            os.path.join(os.path.dirname(journal_path), "backup-%s" % session),
            ignore_errors=True,
        )
    if os.path.isfile(journal_path):
        os.remove(journal_path)
