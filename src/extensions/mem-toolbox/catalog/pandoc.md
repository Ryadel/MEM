# pandoc

- **kind**: cli
- **capability**: convert a document between formats; read or write a Word document
- **min version**: 3.0 — upstream publishes no support policy; 3.12 is current (2026-09-29)
- **purpose**: the universal document converter — Markdown, HTML, DOCX, ODT, EPUB, LaTeX and more, in either
  direction.
- **invocation**: `pandoc <in> -o <out>`, formats inferred from the extensions; `--reference-doc=<file.docx>` to
  apply Word styles
- **licence**: GPL-2.0-or-later, with BSD-3-Clause components, verified 2026-10-05 against
  <https://raw.githubusercontent.com/jgm/pandoc/main/COPYRIGHT>. Run as a separate process it imposes nothing on
  the project — see `TOOL.template.md`, `kind`
- **url**: https://pandoc.org

## Notes

- **PDF output needs an engine pandoc does not include**: LaTeX by default, or `--pdf-engine=typst` and others.
  Without one, `-o out.pdf` fails. With [typst](typst.md) available prefer `--pdf-engine=typst`: a LaTeX
  distribution runs to gigabytes.
- Conversion passes through an internal document model, so what the model lacks — Word text boxes, complex
  tables — is lost in either direction.

## Alternatives

[python-docx](python-docx.md) to edit a Word document in place rather than convert it.
