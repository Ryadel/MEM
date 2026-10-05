# duckdb

- **kind**: cli
- **capability**: query CSV, Parquet or JSON with SQL; read, clean or transform tabular data
- **min version**: 1.0
- **purpose**: an in-process analytical database that queries files directly — the fastest route from "a CSV" to
  "an answer", with no import step.
- **invocation**: `duckdb -c "SELECT * FROM '<file.csv>' LIMIT 10"`
- **licence**: MIT, verified 2026-10-05 against <https://raw.githubusercontent.com/duckdb/duckdb/main/LICENSE>
- **url**: https://duckdb.org

## Notes

- Files are tables: `FROM 'data.csv'`, `FROM 'logs/*.parquet'`. `COPY (<query>) TO 'out.csv'` writes a result.
- A Python client exists as the package `duckdb` (MIT, <https://github.com/duckdb/duckdb-python>): the same engine.
  This entry is the CLI; a project using the client from Python records it as a custom entry.
- Windows builds are `.zip` archives holding one executable.

## Alternatives

[pandas](pandas.md) when the result feeds further Python code. [jq](jq.md) for JSON that is a document, not a table.
