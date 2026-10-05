# python-docx

- **kind**: library
- **capability**: read or write a Word document
- **requires**: python
- **package**: `python-docx`
- **import**: `docx`
- **min version**: 1.0
- **purpose**: create or edit `.docx` files in place — paragraphs, tables, styles, headers — keeping what is
  already there.
- **invocation**: `from docx import Document`
- **licence**: MIT, verified 2026-10-05 against <https://raw.githubusercontent.com/python-openxml/python-docx/master/LICENSE>
- **url**: https://github.com/python-openxml/python-docx

## Notes

- **The package named `docx` is a different, obsolete project.** The import is `docx`, the package is
  `python-docx`; installing the import name is exactly the mistake the `package` field prevents.
- `.docx` only: the legacy binary `.doc` is not read.
- It does not render, so it cannot produce a PDF. Convert with [pandoc](pandoc.md) or an office suite.

## Alternatives

[pandoc](pandoc.md) to produce a `.docx` from Markdown or HTML instead of building it element by element.
