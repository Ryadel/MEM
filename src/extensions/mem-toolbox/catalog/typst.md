# typst

- **kind**: cli
- **capability**: typeset a document to PDF; create a PDF programmatically
- **min version**: 0.15 — still 0.x, so a minor release can change how a document renders; pin the minor
- **purpose**: a modern typesetter — LaTeX-quality output from readable markup, compiled in milliseconds, from
  one executable.
- **invocation**: `typst compile <in.typ> <out.pdf>`; `--font-path <dir>` for fonts not installed system-wide
- **licence**: Apache-2.0, verified 2026-10-05 against <https://raw.githubusercontent.com/typst/typst/main/LICENSE>
- **url**: https://typst.app

## Notes

- Ships as a single executable in a `.zip`, which fits the tools-root convention directly.
- Package imports (`#import "@preview/..."`) are downloaded on first use — a network access at compile time. Say
  so before compiling a document that imports one.
- Data can be read at compile time with `json()` and `csv()`, so a template plus a data file replaces generated
  markup.

## Alternatives

[reportlab](reportlab.md) when the layout is computed from data rather than written as a document.
[pandoc](pandoc.md) can drive typst as its PDF engine.
