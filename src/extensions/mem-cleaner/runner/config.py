"""Reads the extensions_cleaner_* options out of MEM.config.md.

MEM.config.md is a Markdown page with one fenced yaml block of settings. Only
the keys this extension owns are read; everything else is left alone, including
keys belonging to the core or to another extension.

An absent or unreadable configuration yields defaults, and the default for
autonomy is `manual` -- the mode that does nothing. A missing key is never
consent.
"""

from __future__ import annotations

import os

from . import frontmatter


PREFIX = "extensions_cleaner_"

MODES = ("automatic", "confirm", "manual")

# Core keys this extension is allowed to read. It never writes them, and it
# never invents a value for one: see NOT_A_COMMAND.
CORE_KEYS = ("build_command", "test_command", "default_branch")

# Values MEM uses to mean "there isn't one" or "work it out yourself". Working
# it out is exactly what this extension must not do, so all of them mean the
# command is unavailable.
NOT_A_COMMAND = ("", "none", "auto-detect", "null", "n/a")

DEFAULTS = {
    "enabled": True,
    "mode": "manual",
    "pipeline": "safe",
    "max_rewrite_stages": 1,
    "validation": "syntax",
    "fail_policy": "restore",
    "include": [],
    "exclude": [],
    "update_daily_log": False,
    # Validation layer
    "format_command": None,
    "project_root": "..",
    "validation_timeout": 600,
}


class ConfigError(ValueError):
    """The configuration is present but says something invalid."""


class Config:
    def __init__(self, values, kb_root, source=None, problems=None, core=None):
        self.kb_root = kb_root
        self.source = source
        self.core = dict(core or {})
        # Reasons the configuration could not be read in full. Never empty and
        # ignored: the CLI reports them, because a configuration that silently
        # became defaults is the same failure as a missing key being read as
        # consent.
        self.problems = list(problems or [])
        merged = dict(DEFAULTS)
        merged.update(values)

        self.enabled = bool(merged["enabled"])
        self.pipeline = str(merged["pipeline"])
        self.validation = str(merged["validation"])
        self.fail_policy = str(merged["fail_policy"])
        self.include = list(merged["include"] or [])
        self.exclude = list(merged["exclude"] or [])
        self.update_daily_log = bool(merged["update_daily_log"])

        mode = merged["mode"]
        # An unreadable or unknown mode degrades to `manual` rather than
        # failing: refusing to start would be a worse answer than doing nothing.
        self.mode = mode if mode in MODES else "manual"
        self.mode_was_defaulted = mode not in MODES

        try:
            self.max_rewrite_stages = int(merged["max_rewrite_stages"])
        except (TypeError, ValueError):
            raise ConfigError("max_rewrite_stages must be an integer")
        if self.max_rewrite_stages < 0:
            raise ConfigError("max_rewrite_stages must not be negative")

        self.format_command = _command(merged["format_command"])
        self.project_root_setting = str(merged["project_root"])

        try:
            self.validation_timeout = int(merged["validation_timeout"])
        except (TypeError, ValueError):
            raise ConfigError("validation_timeout must be an integer number of seconds")
        if self.validation_timeout <= 0:
            raise ConfigError("validation_timeout must be positive")

    @property
    def extension_root(self):
        return os.path.join(self.kb_root, "extensions", "mem-cleaner")

    @property
    def project_root(self):
        """Where validation commands run.

        Defaults to the knowledge base's parent, which is right for the common
        <project>/MEM/ layout and wrong for anything else -- so it is reported
        in STATUS rather than assumed, and overridable.
        """
        return os.path.abspath(os.path.join(self.kb_root, self.project_root_setting))

    @property
    def build_command(self):
        return _command(self.core.get("build_command"))

    @property
    def test_command(self):
        return _command(self.core.get("test_command"))

    def describe(self):
        return [
            ("enabled", self.enabled),
            ("mode", self.mode),
            ("pipeline", self.pipeline),
            ("max_rewrite_stages", self.max_rewrite_stages),
            ("validation", self.validation),
            ("fail_policy", self.fail_policy),
            ("project_root", self.project_root),
            ("format_command", self.format_command or "(none)"),
            ("build_command", self.build_command or "(none)"),
            ("test_command", self.test_command or "(none)"),
        ]


def _command(value):
    """Normalise a configured command, or None when there isn't one.

    MEM writes `auto-detect` where a project has not said. That is not a
    command and must never be treated as one: guessing a test command and
    running it is both a wrong answer and an unrequested side effect.
    """
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in NOT_A_COMMAND:
        return None
    return text


def load(kb_root):
    """Load configuration for the knowledge base rooted at kb_root."""
    path = os.path.join(kb_root, "MEM.config.md")
    if not os.path.isfile(path):
        return Config({}, kb_root, source=None)

    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()

    block = _first_yaml_block(text)
    if block is None:
        return Config(
            {},
            kb_root,
            source=path,
            problems=["%s: no yaml configuration block found" % path],
        )

    problems = []
    try:
        data = frontmatter.parse(block)
    except frontmatter.FrontMatterError as error:
        # The whole block failed, which may well be another extension's key
        # using a construct this parser does not accept. Fall back to reading
        # only the keys this extension owns, and report either way. What must
        # never happen is defaulting in silence.
        data, recovered = _recover(block)
        problems.append("%s: %s" % (path, error))
        if recovered:
            problems.append(
                "read %d extensions_cleaner_* key(s) line by line; "
                "any other setting was ignored" % recovered
            )
        else:
            problems.append(
                "no extensions_cleaner_* key could be read, so defaults are in effect"
            )

    values = {}
    core = {}
    for key, value in (data or {}).items():
        if not isinstance(key, str):
            continue
        if key.startswith(PREFIX):
            values[key[len(PREFIX) :]] = value
        elif key in CORE_KEYS:
            core[key] = value
    return Config(values, kb_root, source=path, problems=problems, core=core)


def _recover(block):
    """Extract only this extension's simple 'key: value' lines from a block.

    Used when the block as a whole cannot be parsed. Nested settings are not
    recoverable this way and are left out rather than half-read.
    """
    values = {}
    for number, line in enumerate(block.splitlines(), start=1):
        stripped = line.strip()
        if not (stripped.startswith(PREFIX) or stripped.split(":")[0] in CORE_KEYS):
            continue
        key, sep, inline = stripped.partition(":")
        if not sep or not inline.strip():
            continue
        try:
            values[key.strip()] = frontmatter.parse("%s: %s" % (key.strip(), inline.strip()))[
                key.strip()
            ]
        except (frontmatter.FrontMatterError, KeyError):
            continue
    return values, len(values)


def find_kb_root(start=None):
    """Locate the knowledge base this runner belongs to.

    The runner is installed *inside* a knowledge base, at
    <KB_ROOT>/extensions/mem-cleaner/runner/, so its own location identifies
    that base regardless of where the command was invoked from. That is checked
    first: the documented invocation names the runner by path, and a user
    running it from elsewhere should not get a different answer, or none.

    The working directory is tried second, which keeps the command usable from
    inside a knowledge base whose runner is somewhere else.

    Returns None when neither yields one, which the CLI reports rather than
    guessing a location.
    """
    candidates = []
    if start is not None:
        candidates.append(start)
    else:
        candidates.append(os.path.dirname(os.path.abspath(__file__)))
        candidates.append(os.getcwd())

    for candidate in candidates:
        found = _walk_up(candidate)
        if found is not None:
            return found
    return None


def _walk_up(start):
    current = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(current, "MEM.md")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _first_yaml_block(text):
    lines = text.splitlines()
    collecting = False
    collected = []
    for line in lines:
        stripped = line.strip()
        if not collecting and stripped.startswith("```") and "yaml" in stripped:
            collecting = True
            continue
        if collecting:
            if stripped.startswith("```"):
                return "\n".join(collected)
            collected.append(line)
    return None
