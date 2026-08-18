"""Per-host transient storage: journals, backups, session records.

None of this belongs in the knowledge base. The knowledge base is committed and
shared; a journal describes one interrupted run on one machine, and a backup is
a copy of somebody's source file. Both are re-derivable or worthless elsewhere,
and neither should ever reach a repository.

Location follows the platform convention, keyed by a digest of the knowledge
base path so two bases on one machine never share state.
"""

from __future__ import annotations

import hashlib
import os


APP = "mem-cleaner"


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def hash_file(path):
    """Digest of a file's exact bytes, or None when it does not exist.

    Bytes, not text: encoding and line endings are part of what must not change
    silently, so they are part of what is compared.
    """
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def state_root():
    """The base directory for this runner's transient state."""
    override = os.environ.get("MEM_CLEANER_STATE")
    if override:
        return os.path.abspath(override)

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP)

    base = os.environ.get("XDG_STATE_HOME")
    if base:
        return os.path.join(base, APP)
    return os.path.join(os.path.expanduser("~"), ".local", "state", APP)


def for_kb(kb_root):
    """State directory for one knowledge base. Created on demand."""
    key = hash_bytes(os.path.abspath(kb_root).encode("utf-8"))[:16]
    path = os.path.join(state_root(), key)
    os.makedirs(path, exist_ok=True)
    return path


def describe(kb_root):
    """Human-readable location, for STATUS output."""
    return os.path.join(state_root(), hash_bytes(os.path.abspath(kb_root).encode("utf-8"))[:16])
