"""Validation: the checks that decide whether a replacement is kept.

Two layers. **Minimum** is unconditional and file-local: is the candidate the
same *kind* of artifact as the original? **Full** adds the project's own
formatter, build and tests, run against the tree with candidates installed,
because a test suite cannot see a temporary copy.

Neither layer asks whether the result is *better*. That is not something a
cleaner can know.

The level actually applied is the higher of what configuration asks for and
what the diff demands. And an escalation that cannot be satisfied -- a suite
demanded where no test command is configured -- is a **refusal, not a
downgrade**. Silently accepting a weaker check is how a guarantee stops meaning
anything.
"""

from __future__ import annotations

import ast
import os
import shlex
import subprocess


class Finding:
    """One validation outcome. `ok` false means the candidate is rejected."""

    def __init__(self, check, ok, detail=""):
        self.check = check
        self.ok = ok
        self.detail = detail

    def __str__(self):
        mark = "ok" if self.ok else "FAILED"
        return "%-22s %s%s" % (self.check, mark, (": " + self.detail) if self.detail else "")


class Report:
    def __init__(self, findings):
        self.findings = findings

    @property
    def ok(self):
        return all(f.ok for f in self.findings)

    @property
    def failures(self):
        return [f for f in self.findings if not f.ok]


# Extensions whose syntax this runner can check itself. Anything else is
# reported as unparsed rather than silently treated as valid: "no parser" and
# "parses cleanly" are different answers and must not look alike.
PARSERS = {".py": "python"}


def minimum(original_path, candidate_path):
    """Validate a candidate against the original it would replace."""
    findings = []

    if not os.path.isfile(candidate_path):
        return Report([Finding("candidate exists", False, "no candidate file")])

    original = _read(original_path)
    candidate = _read(candidate_path)

    findings.append(_non_empty(original, candidate))
    findings.append(_encoding(candidate))
    findings.append(_line_endings(original, candidate))
    findings.append(_trailing_newline(original, candidate))
    findings.append(_syntax(original_path, candidate))
    return Report(findings)


def _read(path):
    if not os.path.isfile(path):
        return b""
    with open(path, "rb") as handle:
        return handle.read()


def _non_empty(original, candidate):
    # An empty result from a non-empty input is the signature of a provider
    # that crashed after opening its output file. It is never a valid cleanup.
    if original and not candidate:
        return Finding("non-empty", False, "original had content, candidate is empty")
    return Finding("non-empty", True)


def _encoding(candidate):
    try:
        candidate.decode("utf-8")
    except UnicodeDecodeError as error:
        return Finding("encoding", False, "candidate is not valid UTF-8 (%s)" % error.reason)
    return Finding("encoding", True)


def _line_endings(original, candidate):
    before = _eol_profile(original)
    after = _eol_profile(candidate)
    if before != after:
        return Finding(
            "line endings",
            False,
            "%s became %s" % (_eol_name(before), _eol_name(after)),
        )
    return Finding("line endings", True, _eol_name(after))


def _eol_profile(data):
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n") - crlf
    cr = data.count(b"\r") - crlf
    if crlf and not lf and not cr:
        return "crlf"
    if lf and not crlf and not cr:
        return "lf"
    if not (crlf or lf or cr):
        return "none"
    return "mixed"


def _eol_name(profile):
    return {"crlf": "CRLF", "lf": "LF", "none": "no line endings", "mixed": "mixed"}[profile]


def _trailing_newline(original, candidate):
    # Adding or removing a final newline is a real diff in every review tool,
    # and it is never what a cleaner was asked to do.
    before = original.endswith(b"\n")
    after = candidate.endswith(b"\n")
    if before != after:
        return Finding(
            "trailing newline",
            False,
            "added" if after else "removed",
        )
    return Finding("trailing newline", True)


def _syntax(original_path, candidate):
    language = PARSERS.get(os.path.splitext(original_path)[1].lower())
    if language is None:
        # Not a failure, and deliberately not silent. A pipeline that needs a
        # stronger guarantee escalates; it must not read this as "valid".
        return Finding("syntax", True, "no parser for this file type; unchecked")
    try:
        ast.parse(candidate.decode("utf-8"))
    except (SyntaxError, ValueError) as error:
        return Finding("syntax", False, "%s does not parse: %s" % (language, error))
    return Finding("syntax", True, language)


def parser_available(path):
    """Whether minimum validation can actually check this file's syntax."""
    return os.path.splitext(path)[1].lower() in PARSERS


# -- the full layer --------------------------------------------------------

SYNTAX = "syntax"
FORMAT = "format"
PROJECT = "project"
TESTS = "tests"

# Ordered weakest to strongest. Escalation moves right, never left.
LEVELS = (SYNTAX, FORMAT, PROJECT, TESTS)


class Unsatisfiable(RuntimeError):
    """The required level needs a command this project has not configured."""


def rank(level):
    try:
        return LEVELS.index(level)
    except ValueError:
        # An unknown level is treated as the strongest rather than ignored:
        # misreading configuration must not weaken a check.
        return len(LEVELS) - 1


def required_level(configured, demanded=None):
    """The level actually applied: the stronger of configuration and diff."""
    if demanded is None:
        return configured if configured in LEVELS else TESTS
    return LEVELS[max(rank(configured), rank(demanded))]


# What each level is named after, and where that command comes from.
_LEVEL_COMMAND = {
    FORMAT: ("format", "extensions_cleaner_format_command"),
    PROJECT: ("project", "build_command"),
    TESTS: ("tests", "test_command"),
}


def _command_for(name, cfg):
    return {
        "format": cfg.format_command,
        "project": cfg.build_command,
        "tests": cfg.test_command,
    }[name]


def commands_for(level, cfg):
    """The (name, command_or_None) pairs a level runs, weakest first.

    A level requires **only the command it is named after**. Formatter, build
    and tests are independent guarantees, not a ladder of the same one: a
    project with tests and no formatter can legitimately ask for `tests`.

    Lower-level commands are included when configured and reported as unchecked
    when not -- which is not a silent downgrade, because it is reported.

    Raises Unsatisfiable when the level's own command is missing. `auto-detect`
    is not a command; see config.NOT_A_COMMAND.
    """
    if rank(level) <= rank(SYNTAX):
        return []

    own_name, own_setting = _LEVEL_COMMAND[level]
    if _command_for(own_name, cfg) is None:
        raise Unsatisfiable(
            "level %r needs %s, and it is not set (or is 'auto-detect', which "
            "is not a command)" % (level, own_setting)
        )

    pairs = []
    for candidate in LEVELS[1 : rank(level) + 1]:
        name, _ = _LEVEL_COMMAND[candidate]
        pairs.append((name, _command_for(name, cfg)))
    return pairs


def split_command(command):
    """Split a configured command string into an argv vector.

    Neither shlex mode is correct on Windows by itself. `posix=True` treats a
    backslash as an escape, so `C:\\tools\\x.exe` becomes `C:toolsx.exe`.
    `posix=False` keeps backslashes but also keeps the quotes *inside* each
    token, so `-c "import sys"` reaches the program as a literal quoted string
    -- which silently succeeds instead of running what was asked.

    So on Windows: split without posix rules, then strip one matched pair of
    surrounding quotes per token. Both a quoted argument and a Windows path
    survive that.
    """
    if os.name != "nt":
        return shlex.split(command, posix=True)
    tokens = shlex.split(command, posix=False)
    return [_unquote(token) for token in tokens]


def _unquote(token):
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


# Bare tokens that only mean anything to a shell. Detected after splitting, so
# the same characters inside a quoted argument are left alone.
SHELL_CONSTRUCTS = ("|", "||", "&", "&&", ";", ">", ">>", "<", "2>", "2>&1")


def _shell_construct(argv):
    for token in argv:
        if token in SHELL_CONSTRUCTS:
            return token
    return None


def run_command(command, cwd, timeout):
    """Run one configured command without a shell, and report the outcome.

    No shell: a command needing pipes or chaining belongs in a script the
    project owns, where it is reviewable as a file rather than as a
    configuration string.
    """
    try:
        argv = split_command(command)
    except ValueError as error:
        return Finding("command", False, "cannot parse %r: %s" % (command, error))
    if not argv:
        return Finding("command", False, "empty command")

    shell_token = _shell_construct(argv)
    if shell_token:
        # Without a shell these are just extra arguments, so the command runs,
        # does something other than what was written, and very likely exits
        # zero. A false pass is worse than a refusal.
        return Finding(
            "command",
            False,
            "%r uses the shell construct %r, and commands run without a shell. "
            "Put it in a script the project owns and configure that instead."
            % (command, shell_token),
        )

    if not os.path.isdir(cwd):
        return Finding("command", False, "working directory does not exist: %s" % cwd)

    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except FileNotFoundError:
        return Finding("command", False, "%r not found" % argv[0])
    except subprocess.TimeoutExpired:
        return Finding("command", False, "%r timed out after %ds" % (command, timeout))
    except OSError as error:
        return Finding("command", False, "%r could not run: %s" % (command, error))

    if completed.returncode != 0:
        tail = _tail(completed.stdout)
        return Finding("command", False, "%r exited %d%s" % (command, completed.returncode, tail))
    return Finding("command", True, command)


def full(pairs, cfg, level):
    """Validate at `level`. `pairs` is [(original_path, installed_path), ...].

    Candidates are already installed at their real paths, which is what lets a
    build or a test suite see them at all.
    """
    findings = []
    for original, installed in pairs:
        report = minimum(original, installed)
        for finding in report.findings:
            finding.check = "%s: %s" % (os.path.basename(installed), finding.check)
            findings.append(finding)

    for name, command in commands_for(level, cfg):
        if command is None:
            # Reported, never silent. "Not configured" and "passed" are
            # different answers and must not look alike.
            findings.append(Finding(name, True, "not configured; unchecked"))
            continue
        finding = run_command(command, cfg.project_root, cfg.validation_timeout)
        finding.check = name
        findings.append(finding)

    return Report(findings)


def _tail(output, limit=400):
    if not output:
        return ""
    text = output.decode("utf-8", "replace").strip()
    if not text:
        return ""
    if len(text) > limit:
        text = "..." + text[-limit:]
    return "\n      " + text.replace("\n", "\n      ")
