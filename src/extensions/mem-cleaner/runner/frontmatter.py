"""Front-matter parsing, restricted to a documented subset.

The runner ships as source into a consuming repository and must not require
a YAML library. That constraint is the whole reason this module exists.

The subset is deliberately small: scalars, nested mappings by indentation, and
lists of scalars or of mappings. Anything outside it raises FrontMatterError
rather than being interpreted. A mis-parsed pipeline is a mis-executed one, so
guessing is the one behaviour that is never acceptable here.
"""

from __future__ import annotations


class FrontMatterError(ValueError):
    """The document is outside the accepted subset, or malformed."""


_TRUE = ("true", "yes", "on")
_FALSE = ("false", "no", "off")

# Constructs that are valid YAML but outside this subset. Rejected by name so
# the error says what is unsupported instead of failing somewhere downstream.
_UNSUPPORTED = {
    "|": "block scalars",
    ">": "folded scalars",
    "&": "anchors",
    "*": "aliases",
    "!": "tags",
    "{": "non-empty flow mappings",
    "[": "non-empty flow sequences",
}


def split(text):
    """Return (front_matter_text, body). Both may be empty.

    Front matter is delimited by '---' on its own line, at the very start of
    the document. A file without it is body-only, which is not an error.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return "", text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1 :])
    raise FrontMatterError("front matter opened with '---' but never closed")


def parse(text):
    """Parse the accepted subset into dicts, lists, str, bool, int and None."""
    lines = []
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append((number, len(raw) - len(raw.lstrip(" ")), stripped, raw))
    if not lines:
        return {}
    if "\t" in text:
        raise FrontMatterError("tabs are not valid indentation")
    value, index = _parse_block(lines, 0, lines[0][1])
    if index != len(lines):
        number = lines[index][0]
        raise FrontMatterError("line %d: unexpected indentation" % number)
    return value


def load(text):
    """Convenience: split, parse the front matter, return (data, body)."""
    front, body = split(text)
    return parse(front), body


def _parse_block(lines, index, indent):
    """Dispatch to a list or mapping parser based on the first entry."""
    if lines[index][2].startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_mapping(lines, index, indent):
    result = {}
    while index < len(lines):
        number, current_indent, content, _ = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise FrontMatterError("line %d: unexpected indentation" % number)
        if content.startswith("- "):
            raise FrontMatterError("line %d: list item inside a mapping" % number)
        key, sep, inline = content.partition(":")
        if not sep:
            raise FrontMatterError("line %d: expected 'key: value'" % number)
        key = key.strip()
        if not key:
            raise FrontMatterError("line %d: empty key" % number)
        if key in result:
            raise FrontMatterError("line %d: duplicate key %r" % (number, key))
        inline = inline.strip()
        if inline:
            result[key] = _scalar(inline, number)
            index += 1
            continue
        # No inline value: either a nested block, or an explicit empty value.
        if index + 1 < len(lines) and lines[index + 1][1] > current_indent:
            result[key], index = _parse_block(lines, index + 1, lines[index + 1][1])
        else:
            result[key] = None
            index += 1
    return result, index


def _parse_list(lines, index, indent):
    result = []
    while index < len(lines):
        number, current_indent, content, raw = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise FrontMatterError("line %d: unexpected indentation" % number)
        if not content.startswith("- "):
            break
        item = content[2:].strip()
        if not item:
            raise FrontMatterError("line %d: empty list item" % number)
        if ":" in item and not _is_quoted(item):
            # 'key: value' on the dash line starts a mapping item. Its keys are
            # indented to where the text after '- ' begins.
            item_indent = raw.index("- ") + 2
            synthetic = [(number, item_indent, item, raw)]
            index += 1
            while index < len(lines) and lines[index][1] >= item_indent:
                if lines[index][2].startswith("- ") and lines[index][1] == item_indent:
                    break
                synthetic.append(lines[index])
                index += 1
            mapping, consumed = _parse_mapping(synthetic, 0, item_indent)
            if consumed != len(synthetic):
                raise FrontMatterError("line %d: unexpected indentation" % number)
            result.append(mapping)
            continue
        result.append(_scalar(item, number))
        index += 1
    return result, index


def _is_quoted(value):
    return len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'"


def _scalar(value, number):
    if _is_quoted(value):
        return value[1:-1]
    # Empty flow collections are accepted because they are unambiguous, and
    # because '[]' is the only way to write an empty list on one line. Non-empty
    # flow collections stay unsupported: those have quoting and nesting rules
    # this parser does not implement, and guessing at them is worse than
    # refusing.
    if value == "[]":
        return []
    if value == "{}":
        return {}
    first = value[0]
    if first in _UNSUPPORTED:
        raise FrontMatterError(
            "line %d: %s are not supported" % (number, _UNSUPPORTED[first])
        )
    lowered = value.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    if lowered in ("null", "~"):
        return None
    try:
        return int(value)
    except ValueError:
        return value
