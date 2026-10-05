# jq

- **kind**: cli
- **capability**: query or transform JSON
- **min version**: 1.7 — upstream publishes no support policy; 1.8.2 is current (2026-06-20)
- **purpose**: filter, reshape and extract from JSON in one expression — the tool for an API response or a config
  file.
- **invocation**: `jq '<filter>' <file.json>`; `-r` for raw strings
- **licence**: MIT, verified 2026-10-05 against <https://raw.githubusercontent.com/jqlang/jq/master/COPYING>
- **url**: https://jqlang.org

## Notes

- Shell quoting is the usual failure. In PowerShell, put the filter in a file and pass `-f <file>` rather than
  fighting nested quotes.
- Ships as one executable per platform.

## Alternatives

[duckdb](duckdb.md) when the JSON is really a table.
