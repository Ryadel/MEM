# pandas

- **kind**: library
- **capability**: read, clean or transform tabular data; read or write an Excel workbook
- **requires**: python
- **package**: `pandas`
- **min version**: 2.2 — 3.0 (2026-01-21) is current, requires Python 3.11, and changes behaviour; read its
  release notes before moving code across
- **purpose**: dataframes — the default for loading a CSV or a sheet, reshaping it, and writing it back.
- **invocation**: `import pandas as pd`, then `pd.read_csv(path)`
- **licence**: BSD-3-Clause, verified 2026-10-05 against <https://raw.githubusercontent.com/pandas-dev/pandas/main/LICENSE>
- **url**: https://pandas.pydata.org

## Notes

- Heavy: it pulls numpy. For one query over a file, [duckdb](duckdb.md) is lighter and faster.
- `read_csv` infers types. Leading zeros, codes and identifiers become numbers unless `dtype=str` is passed for
  those columns — the commonest silent corruption here.
- Excel I/O needs [openpyxl](openpyxl.md) in the same environment.

## Alternatives

[duckdb](duckdb.md) for SQL over files without loading them first.
