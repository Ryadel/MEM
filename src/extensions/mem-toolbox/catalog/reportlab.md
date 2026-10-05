# reportlab

- **kind**: library
- **capability**: create a PDF programmatically
- **requires**: python
- **package**: `reportlab`
- **min version**: 4.0 — the 4.x line runs on Python 3.11; 5.0, released 2026-06-18, is current
- **purpose**: the default for generating a PDF from data — reports, invoices, labels — where the layout is
  computed rather than typeset from a document.
- **invocation**: imported from a script run by the environment's interpreter: `from reportlab.platypus import
  SimpleDocTemplate, Paragraph` for flowing documents, `from reportlab.pdfgen import canvas` for absolute placement
- **licence**: BSD-3-Clause, verified 2026-10-05 against the `LICENSE` in the 5.0.1 source distribution
  (<https://pypi.org/pypi/reportlab/json>); PyPI metadata says only "BSD license". **The open-source toolkit
  only**: the commercial ReportLab PLUS / RML is a separate product and depends on pyRXP, which is GPL
- **url**: https://www.reportlab.com/

## Notes

- Two APIs. `platypus` flows content across pages and paginates; `canvas` draws at coordinates and leaves
  pagination to you. Start with `platypus` unless the layout is a fixed form.
- The built-in fonts are the PDF standard 14, which cover Latin text only. Anything else — CJK, symbols, most
  non-Western scripts — needs a TrueType font registered with `pdfmetrics.registerFont(TTFont(...))`, or it
  renders as black boxes.
- Coordinates start at the **bottom-left**, in points.
- The source repository is not on GitHub; documentation is at <https://docs.reportlab.com/>.

## Alternatives

[typst](typst.md) when the PDF is a *document* — prose, headings, references — rather than computed output.
[pandoc](pandoc.md) when the content already exists in another format.
