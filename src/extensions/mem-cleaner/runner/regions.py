"""Classifying a file into regions, and holding a stage to the one it asked for.

"Comments and docstrings are safe" is false, which is why this module exists.
A comment is frequently machine-readable, and a docstring is reachable at run
time. So a file is classified three ways:

    prose      narrative comments and Markdown text
    directive  # type: ignore, # noqa, //go:build, shebangs, coding lines
    runtime    docstrings, string literals, fenced code, anything executed or
               compared byte for byte

plus `code`, which no deterministic stage may touch at all.

**Doubt escalates.** An unrecognised `word:` comment prefix is treated as a
directive, an unknown file type has no classifier at all, and neither is ever
treated as prose. Being wrong in that direction only means "do not touch".

The scope is not a request. `verify()` compares what a stage actually changed
against what it was allowed to change, so the boundary is a mechanism rather
than a promise -- which was the whole point of the criticism that produced it.
"""

from __future__ import annotations

import io
import os
import re
import tokenize


PROSE = "prose"
DIRECTIVE = "directive"
RUNTIME = "runtime"
CODE = "code"
UNKNOWN = "unknown"

# Which kinds a stage declaring a given scope may touch.
TOUCHABLE = {
    "prose": (PROSE,),
    "runtime": (PROSE, RUNTIME),
    "any": (PROSE, RUNTIME, CODE),
}


class Region:
    def __init__(self, start, end, kind):
        self.start = start
        self.end = end
        self.kind = kind

    def __repr__(self):
        return "<%s %d:%d>" % (self.kind, self.start, self.end)


class Classification:
    def __init__(self, path, regions, language, note=""):
        self.path = path
        self.regions = regions
        self.language = language
        self.note = note

    @property
    def usable(self):
        """False when nothing here may be touched by a scoped stage."""
        return self.language != UNKNOWN

    def kind_at(self, offset):
        for region in self.regions:
            if region.start <= offset < region.end:
                return region.kind
        return CODE if self.usable else UNKNOWN

    def summary(self):
        counts = {}
        for region in self.regions:
            counts[region.kind] = counts.get(region.kind, 0) + 1
        return counts


# -- Python ----------------------------------------------------------------

# A comment whose body looks like `word:` is a tool directive far more often
# than it is prose, so unknown ones are classified as directives too. The named
# ones are here for documentation, not for the decision.
KNOWN_DIRECTIVES = (
    "type", "noqa", "pragma", "pylint", "mypy", "fmt", "isort", "yapf",
    "ruff", "flake8", "coverage", "coding", "nosec",
)

_DIRECTIVE_RE = re.compile(r"^#\s*-?\*?-?\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*:")


class _ByteOffsets:
    """Convert (row, character column) to a **byte** offset.

    Load-bearing, not a convenience. Python's tokenizer and every string index
    here count characters; `changed_spans` and `verify` compare bytes. On a file
    containing any non-ASCII character the two drift apart, and a byte change
    outside a comment can land, in character space, inside one -- which would
    accept a forbidden edit as prose. Mixing the two units is a security bug,
    so the conversion happens once, here, and the classifiers only ever emit
    byte offsets.
    """

    def __init__(self, text):
        self.lines = text.splitlines(keepends=True)
        self.starts = []
        running = 0
        for line in self.lines:
            self.starts.append(running)
            running += len(line.encode("utf-8"))
        self.total = running

    def at(self, row, col):
        # ENDMARKER and a trailing NEWLINE can sit one row past the last line.
        index = row - 1
        if index < 0:
            return 0
        if index >= len(self.lines):
            return self.total
        line = self.lines[index]
        col = max(0, min(col, len(line)))
        return self.starts[index] + len(line[:col].encode("utf-8"))

    def in_line(self, index, col):
        """Byte offset of a character column within line `index` (0-based)."""
        return self.at(index + 1, col)


def _python(data):
    text = data.decode("utf-8")
    regions = []
    offsets = _ByteOffsets(text)

    def offset_of(row, col):
        return offsets.at(row, col)

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError) as error:
        return Classification(None, [], UNKNOWN, "does not tokenize: %s" % error)

    for token in tokens:
        if token.type == tokenize.COMMENT:
            start = offset_of(*token.start)
            body = token.string.strip()
            if body.startswith("#!") and start == 0:
                kind = DIRECTIVE
            elif _DIRECTIVE_RE.match(body):
                kind = DIRECTIVE
            else:
                kind = PROSE
            regions.append(Region(start, offset_of(*token.end), kind))

        elif token.type == tokenize.STRING:
            # Every string literal is runtime: docstrings are reachable as
            # __doc__ and executed by doctest, and ordinary literals may carry
            # URLs, SQL, protocol values or snapshot text.
            regions.append(
                Region(offset_of(*token.start), offset_of(*token.end), RUNTIME)
            )

    return Classification(None, sorted(regions, key=lambda r: r.start), "python")


# -- Markdown and plain text -----------------------------------------------

_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _markdown(data):
    text = data.decode("utf-8")
    regions = []
    offsets = _ByteOffsets(text)
    in_fence = False
    fence_marker = None

    for index, line in enumerate(offsets.lines):
        start = offsets.starts[index]
        end = start + len(line.encode("utf-8"))
        stripped = line.rstrip("\r\n")
        match = _FENCE_RE.match(stripped)

        if in_fence:
            regions.append(Region(start, end, RUNTIME))
            if match and match.group(1)[0] == fence_marker[0] and len(match.group(1)) >= len(fence_marker):
                in_fence = False
                fence_marker = None
            continue

        if match:
            in_fence = True
            fence_marker = match.group(1)
            regions.append(Region(start, end, RUNTIME))
            continue

        # An indented block may be code or a list continuation, and telling
        # them apart needs a real Markdown parser. Classified as runtime, which
        # is the direction that declines to touch it.
        if stripped.startswith("    ") and stripped.strip():
            regions.append(Region(start, end, RUNTIME))
            continue

        cursor = 0
        for span in _INLINE_CODE_RE.finditer(stripped):
            span_start = offsets.in_line(index, span.start())
            span_end = offsets.in_line(index, span.end())
            if span.start() > cursor:
                regions.append(Region(offsets.in_line(index, cursor), span_start, PROSE))
            regions.append(Region(span_start, span_end, RUNTIME))
            cursor = span.end()
        regions.append(Region(offsets.in_line(index, cursor), end, PROSE))

    note = "unterminated code fence; the rest of the file is runtime" if in_fence else ""
    return Classification(None, regions, "markdown", note)


CLASSIFIERS = {
    ".py": _python,
    ".md": _markdown,
    ".markdown": _markdown,
    ".txt": _markdown,
}


def classify(path, data):
    """Classify a file. An unknown type yields no touchable region at all."""
    handler = CLASSIFIERS.get(os.path.splitext(path)[1].lower())
    if handler is None:
        return Classification(
            path, [], UNKNOWN, "no classifier for this file type"
        )
    try:
        result = handler(data)
    except UnicodeDecodeError:
        return Classification(path, [], UNKNOWN, "not valid UTF-8")
    result.path = path
    return result


def touchable_ranges(classification, scope):
    """Byte ranges a stage with this scope may modify."""
    kinds = TOUCHABLE.get(scope, ())
    return [(r.start, r.end) for r in classification.regions if r.kind in kinds]


# -- holding a stage to its scope ------------------------------------------


class Violation:
    def __init__(self, offset, kind, scope):
        self.offset = offset
        self.kind = kind
        self.scope = scope

    def __str__(self):
        return "byte %d is %s, which a %r-scoped stage may not change" % (
            self.offset,
            self.kind,
            self.scope,
        )


def changed_spans(original, candidate):
    """Byte offsets that differ, as (start, end) in the original.

    Deliberately crude: the common prefix and suffix bound the change, and
    everything between is treated as touched. A precise diff would report less,
    and reporting less is the direction that lets a violation through.
    """
    if original == candidate:
        return []
    head = 0
    limit = min(len(original), len(candidate))
    while head < limit and original[head] == candidate[head]:
        head += 1
    tail = 0
    while (
        tail < limit - head
        and original[len(original) - 1 - tail] == candidate[len(candidate) - 1 - tail]
    ):
        tail += 1
    return [(head, max(head, len(original) - tail))]


def verify(path, original, candidate, scope):
    """Check that a change respected its declared scope.

    Returns (violations, touched_kinds). An empty violation list is the only
    thing that lets a candidate through.
    """
    classification = classify(path, original)
    if not classification.usable:
        return (
            [Violation(0, UNKNOWN, scope)],
            {UNKNOWN},
        )

    violations = []
    touched = set()
    allowed = TOUCHABLE.get(scope, ())

    for start, end in changed_spans(original, candidate):
        if start == end:
            # A pure insertion sits *between* two bytes. It belongs to what it
            # was appended to, not to what follows: text added at the end of a
            # comment is an edit to that comment, even though the next byte is
            # the newline outside it.
            probe = start - 1 if start > 0 else 0
            offsets = [probe]
        else:
            offsets = range(start, end)

        for offset in offsets:
            kind = classification.kind_at(offset)
            touched.add(kind)
            if kind not in allowed:
                violations.append(Violation(offset, kind, scope))
                break

    return violations, touched


# Which validation level a set of touched kinds demands. Prose alone is cheap;
# anything reaching runtime needs the project's own tests, because a snapshot
# or a fixture compares bytes and survives every syntax check.
DEMANDS = {
    PROSE: "syntax",
    DIRECTIVE: "tests",
    RUNTIME: "tests",
    CODE: "tests",
    UNKNOWN: "tests",
}


# -- extraction and reinsertion --------------------------------------------

# Joins extracted regions into one payload. ASCII letters and punctuation
# only: a Layer-A cleaner removes invisible characters and normalises exotic
# spaces, and touches none of these. The count is checked after cleaning, so a
# provider that did mangle it is caught rather than trusted.
SENTINEL = b"\n@@MEM-CLEANER-REGION@@\n"


class ExtractionError(RuntimeError):
    """The payload could not be split back into its regions."""


def extract(data, classification, scope):
    """Return (payload, spans) for the regions a scope permits.

    One payload and one provider invocation, not one per comment: a process
    spawn per region would cost more than the cleaning. The regions are joined
    with a sentinel whose survival is verified on the way back.
    """
    spans = _merged(touchable_ranges(classification, scope))
    if not spans:
        return b"", []
    payload = SENTINEL.join(data[start:end] for start, end in spans)
    return payload, spans


def outside_unchanged(original, result, spans, parts):
    """Check that every byte outside the spliced regions is untouched.

    `reinsert` copies those bytes verbatim, so this asserts its construction
    rather than re-deriving it -- and it is exact, where `verify` is not.

    `verify` bounds a change by the common prefix and suffix, so two edits far
    apart produce one span covering the code between them. That over-reporting
    is safe when verification is the only guard, and wrong once extraction
    *builds* an in-scope result: it would reject a correct one. Use this for a
    spliced result and `verify` for a provider handed the whole file.
    """
    problems = []
    read_original = 0
    read_result = 0
    for (start, end), part in zip(spans, parts):
        gap = start - read_original
        if original[read_original:start] != result[read_result : read_result + gap]:
            problems.append(
                "bytes %d:%d lie outside the permitted regions and were changed"
                % (read_original, start)
            )
        read_original = end
        read_result += gap + len(part)
    if original[read_original:] != result[read_result:]:
        problems.append(
            "bytes after %d lie outside the permitted regions and were changed"
            % read_original
        )
    return problems


def reinsert(data, spans, cleaned):
    """Splice cleaned regions back into the original bytes.

    Everything outside the permitted regions is copied verbatim from the
    original, so a provider that is not region-aware cannot reach it -- which
    is the whole point: it cleans what it is given, and it is given only what
    it may touch.
    """
    if not spans:
        return data
    parts = cleaned.split(SENTINEL)
    if len(parts) != len(spans):
        raise ExtractionError(
            "provider returned %d region(s) for %d sent; the payload separator "
            "did not survive, so nothing can be spliced back safely"
            % (len(parts), len(spans))
        )

    out = bytearray()
    cursor = 0
    for (start, end), replacement in zip(spans, parts):
        out += data[cursor:start]
        out += replacement
        cursor = end
    out += data[cursor:]
    result = bytes(out)

    problems = outside_unchanged(data, result, spans, parts)
    if problems:
        raise ExtractionError("; ".join(problems))
    return result


def _merged(ranges):
    """Sort and merge touching ranges, so a span is never split arbitrarily."""
    ordered = sorted(ranges)
    merged = []
    for start, end in ordered:
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def demanded_level(touched):
    """The strongest level any touched kind demands."""
    order = ("syntax", "format", "project", "tests")
    demanded = "syntax"
    for kind in touched:
        candidate = DEMANDS.get(kind, "tests")
        if order.index(candidate) > order.index(demanded):
            demanded = candidate
    return demanded
