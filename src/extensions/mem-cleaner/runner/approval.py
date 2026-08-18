"""The approval that autonomy rests on, and the conditions that end it.

The mode is chosen once, at installation, and that answer *is* the approval:
`automatic` runs without prompting even where `extensions_require_confirmation`
is true, because that option governs unapproved operations and this one carries
a recorded, named decision.

But an approval is for something specific. Approving "clean my prose with this
provider after the tests pass" is not approving whatever the pipeline is
changed into tomorrow. So the approval records a fingerprint of what was
approved, and lapses when any of it changes:

    the pipeline and its stages
    the provider each stage resolved to, and its version
    the rewrite limit
    the validation level

A lapsed approval degrades to `manual` -- the mode that does nothing -- rather
than to a prompt, because the agent that would see the prompt is the one whose
output is being cleaned.
"""

from __future__ import annotations

import json
import os

from . import state


MODES = ("automatic", "confirm", "manual")


class Approval:
    def __init__(self, kb_root):
        self.kb_root = kb_root
        self.mode = None
        self.fingerprint = None
        self.note = ""
        self._path = os.path.join(state.for_kb(kb_root), "approval.json")
        self._load()

    def _load(self):
        if not os.path.isfile(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (ValueError, OSError):
            # Unreadable is treated as absent, which means `manual`. A record
            # that cannot be read is not consent.
            return
        self.mode = data.get("mode")
        self.fingerprint = data.get("fingerprint")
        self.note = data.get("note", "")

    def save(self, mode, fingerprint, note=""):
        self.mode = mode
        self.fingerprint = fingerprint
        self.note = note
        payload = {
            "version": 1,
            "kb_root": os.path.abspath(self.kb_root),
            "mode": mode,
            "fingerprint": fingerprint,
            "note": note,
        }
        temporary = self._path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(temporary, self._path)

    def revoke(self):
        self.mode = None
        self.fingerprint = None
        if os.path.isfile(self._path):
            os.remove(self._path)


def fingerprint(cfg, pipeline, resolution):
    """A digest of everything the approval was given for."""
    parts = [
        "pipeline=%s@%s" % (pipeline.id, pipeline.version),
        "max_rewrite_stages=%d" % cfg.max_rewrite_stages,
        "validation=%s" % cfg.validation,
    ]
    for stage in pipeline.stages:
        binding = resolution.bindings.get(stage.index)
        if binding is None:
            bound = "builtin:%s" % (stage.builtin or "-")
        else:
            provider, operation = binding
            bound = "%s@%s:%s" % (provider.id, provider.version, operation.name)
        parts.append(
            "stage%d=%s/%s/%s->%s"
            % (
                stage.index,
                stage.role,
                stage.capability or "-",
                getattr(stage, "regions", "any"),
                bound,
            )
        )
    return state.hash_bytes("\n".join(parts).encode("utf-8"))


def check(cfg, approval, current):
    """May an unattended run proceed? Returns (ok, reason).

    Never returns ok for anything but a mode of `automatic` with a matching
    fingerprint. Every other state is a refusal with its own explanation.
    """
    if cfg.mode == "manual":
        return False, "mode is `manual`: nothing runs unattended"
    if cfg.mode == "confirm":
        return (
            False,
            "mode is `confirm`: ask the user, then run without --automatic",
        )
    if approval.mode != "automatic":
        return (
            False,
            "no recorded approval for automatic mode; run `approve --mode automatic`",
        )
    if approval.fingerprint != current:
        return (
            False,
            "the approval has lapsed: the pipeline, a provider, the rewrite "
            "limit or the validation level changed since it was given",
        )
    return True, ""
