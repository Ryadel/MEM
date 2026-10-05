# qpdf

- **kind**: cli
- **capability**: merge, split, rotate or read a PDF; repair, linearise, encrypt or decrypt a PDF
- **min version**: 12 — upstream publishes no support policy; the floor is the current major (12.4.2, 2026-09-27)
- **purpose**: structural PDF transformations that leave content untouched: the tool for a damaged file, for web
  linearisation, and for encryption.
- **invocation**: `qpdf --empty --pages <a.pdf> <b.pdf> -- <out.pdf>` to merge; `qpdf --linearize <in> <out>`;
  `qpdf --check <in>` to inspect
- **licence**: Apache-2.0, verified 2026-10-05 against <https://raw.githubusercontent.com/qpdf/qpdf/main/LICENSE.txt>
- **url**: https://qpdf.sourceforge.io

## Notes

- It rewrites structure, never content, and cannot extract text.
- Windows builds ship as an installer and as a `.zip`; the `.zip` fits the tools-root convention.

## Alternatives

[pypdf](pypdf.md) for the same page operations from inside a script.
