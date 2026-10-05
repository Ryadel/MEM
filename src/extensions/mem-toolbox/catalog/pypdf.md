# pypdf

- **kind**: library
- **capability**: merge, split, rotate or read a PDF; extract text or tables from a PDF
- **requires**: python
- **package**: `pypdf`
- **min version**: 6.0 — released 2025-08; upstream releases often
- **purpose**: pure-Python PDF manipulation with no native dependency: page operations, metadata, form fields,
  plain text extraction.
- **invocation**: `from pypdf import PdfReader, PdfWriter`
- **licence**: BSD-3-Clause, verified 2026-10-05 against <https://raw.githubusercontent.com/py-pdf/pypdf/main/LICENSE>
- **url**: https://github.com/py-pdf/pypdf

## Notes

- It does not render: a page cannot become an image here.
- Text extraction follows the PDF's drawing order, which is not always reading order. For tables use
  [pdfplumber](pdfplumber.md).
- AES-encrypted files also need the `cryptography` package — a second package, and a second approval.
- `PyPDF2` is the abandoned predecessor under a different package name. Never install it as a substitute.

## Alternatives

[qpdf](qpdf.md) for the same page operations from the command line, and for repair, linearisation and encryption.
