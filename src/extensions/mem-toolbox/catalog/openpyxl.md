# openpyxl

- **kind**: library
- **capability**: read or write an Excel workbook
- **requires**: python
- **package**: `openpyxl`
- **min version**: 3.1
- **purpose**: `.xlsx` with formatting, formulas, several sheets and charts — when the workbook itself is the
  deliverable.
- **invocation**: `from openpyxl import load_workbook, Workbook`
- **licence**: MIT, verified 2026-10-05 against <https://foss.heptapod.net/openpyxl/openpyxl/-/raw/branch/3.1/LICENCE.rst>
- **url**: https://openpyxl.readthedocs.io

## Notes

- **It does not evaluate formulas.** `load_workbook(path, data_only=True)` returns the values Excel cached at its
  last save; a workbook openpyxl wrote itself has none until Excel opens it.
- `.xlsx` and `.xlsm` only: the legacy `.xls` is not read.
- The source lives on Heptapod (Mercurial), not GitHub.

## Alternatives

[pandas](pandas.md) when the workbook is only a container for a table and formatting does not matter.
