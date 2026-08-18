"""Running one pipeline stage through one provider.

The provider is invoked as a subprocess with an argument vector built from its
definition. Nothing is imported, nothing is evaluated, and no shell is
involved: the only thing this module knows about a provider is the argv its
definition declares.

Region scoping happens here rather than inside the provider, because a provider
that is not region-aware cleans whatever byte stream it is handed. So it is
handed only what its stage may touch: extract, clean, splice back. Everything
outside the permitted regions is copied verbatim from the original, which makes
the scope a property of the mechanism rather than of the provider's manners.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile

from . import regions as regions_module


DEFAULT_TIMEOUT = 300

# Substituted into a provider's argv, one value per argument, never expanded
# into a command line.
#
# `python` resolves to the interpreter running this runner. A definition that
# hardcoded `python3` would be wrong on Windows, where that name frequently
# does not exist or resolves to a store stub -- and the one interpreter certain
# to exist is the one already executing.
VARIABLES = ("input", "output", "workspace", "language", "agent", "pipeline", "python")


class StageError(RuntimeError):
    """The stage could not run, or its result cannot be trusted."""


class StageResult:
    def __init__(self, path, data, changed, detail="", report=""):
        self.path = path
        self.data = data
        self.changed = changed
        self.detail = detail
        self.report = report


def run_stage(provider, operation, stage, data, path, workspace, timeout=DEFAULT_TIMEOUT):
    """Apply one stage to `data`, returning the new bytes.

    `data` is the content so far, not necessarily the file on disk: stages
    chain, and only the transaction writes anything.
    """
    scope = getattr(stage, "regions", "any")
    classification = regions_module.classify(path, data)

    if not classification.usable:
        raise StageError(
            "%s: %s, so no region may be touched" % (os.path.basename(path), classification.note)
        )

    payload, spans = regions_module.extract(data, classification, scope)
    if not spans:
        return StageResult(path, data, False, "no %s region in this file" % scope)

    cleaned, report = _invoke(provider, operation, payload, workspace, timeout)

    # reinsert copies every out-of-scope byte verbatim and asserts that it did,
    # which is an exact check. `verify` is deliberately not used here: its diff
    # bounds a change by common prefix and suffix, so two edits far apart would
    # be reported as one span covering the untouched code between them --
    # over-reporting that is safe as a sole guard and wrong against a result
    # that was built in scope.
    try:
        result = regions_module.reinsert(data, spans, cleaned)
    except regions_module.ExtractionError as error:
        raise StageError("%s: %s" % (os.path.basename(path), error))

    return StageResult(path, result, result != data, "", report)


def _invoke(provider, operation, payload, workspace, timeout):
    """Write the payload, run the provider's argv, read the result back."""
    if not provider.command:
        raise StageError("provider %r declares no command" % provider.id)

    handle, in_path = tempfile.mkstemp(prefix="mem-cleaner-in-")
    os.close(handle)
    handle, out_path = tempfile.mkstemp(prefix="mem-cleaner-out-")
    os.close(handle)

    try:
        with open(in_path, "wb") as stream:
            stream.write(payload)

        argv = [
            _substitute(argument, in_path, out_path, workspace, operation)
            for argument in [provider.command] + list(provider.args)
        ]

        try:
            completed = subprocess.run(
                argv,
                cwd=workspace,
                timeout=timeout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            raise StageError("%r not found; is the provider installed?" % argv[0])
        except subprocess.TimeoutExpired:
            raise StageError("provider %r timed out after %ds" % (provider.id, timeout))
        except OSError as error:
            raise StageError("provider %r could not run: %s" % (provider.id, error))

        if completed.returncode != 0:
            raise StageError(
                "provider %r exited %d: %s"
                % (
                    provider.id,
                    completed.returncode,
                    _tail(completed.stderr),
                )
            )

        if not os.path.isfile(out_path):
            raise StageError("provider %r wrote no output" % provider.id)
        with open(out_path, "rb") as stream:
            cleaned = stream.read()

        return cleaned, _tail(completed.stderr, limit=600)
    finally:
        for path in (in_path, out_path):
            try:
                os.remove(path)
            except OSError:
                pass


def _substitute(argument, in_path, out_path, workspace, operation):
    """Replace ${...} in one argument. The result is always one argument."""
    values = {
        "input": in_path,
        "output": out_path,
        "workspace": workspace,
        "language": "",
        "agent": "mem-cleaner",
        "pipeline": operation.name,
        "python": sys.executable,
    }
    result = argument
    for name in VARIABLES:
        result = result.replace("${%s}" % name, values[name])
    return result


def _tail(output, limit=300):
    if not output:
        return ""
    text = output.decode("utf-8", "replace").strip()
    if len(text) > limit:
        return "..." + text[-limit:]
    return text


def quote_for_display(argv):
    """A readable rendering of an argv vector, for reports only."""
    return " ".join(shlex.quote(part) for part in argv)
