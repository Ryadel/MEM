# pdfplumber

- **kind**: library
- **capability**: extract text or tables from a PDF
- **requires**: python
- **package**: `pdfplumber`
- **min version**: 0.11
- **purpose**: extraction with positions — words, lines, rectangles — and table detection built on them. Reach
  for it whenever layout matters, which is whenever the PDF holds a table.
- **invocation**: `import pdfplumber`, then `pdfplumber.open(path).pages[n].extract_tables()`
- **licence**: MIT, verified 2026-10-05 against <https://raw.githubusercontent.com/jsvine/pdfplumber/stable/LICENSE.txt>
- **url**: https://github.com/jsvine/pdfplumber

## Notes

- Text-based PDFs only. A scanned PDF has no text to extract, and this returns nothing rather than failing.
- Still 0.x. 0.11.10 pins `pdfminer.six==20260107` (MIT), needs `Pillow>=12.2.0`, and pulls `pypdfium2`, which
  ships a native PDFium binary under "BSD-3-Clause, Apache-2.0, dependency licenses". The approval **should** say
  that these dependencies come with it.
- Table detection is tuned through `table_settings`. The defaults suit ruled tables and miss unruled ones.

## Alternatives

[pypdf](pypdf.md) when plain text is enough and no native dependency is wanted.
