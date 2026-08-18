# Pipelines

Three profiles ship. `extensions_cleaner_pipeline` selects one; a project may add its own under
`custom/pipelines/`.

| Profile | Stages | Rewrite stages | Validation |
|---|---|---|---|
| [`safe`](safe.md) | `unicode` over prose regions, then a syntax check | 0 | Parse; escalates on a runtime-region change |
| `balanced` | not shipped | — | — |
| `full` | not shipped | — | — |

**`safe` is the only profile in 1.0, and it is runnable.** `balanced` and `full` both need a rewrite-capable
provider, and none exists: upstream ships no rewrite model, so there is nothing for those profiles to call.
Listing them with stages would promise something the extension cannot do.

The rules that limit and validate rewrite stages remain in force, unused. They are cheaper to keep than to
re-derive when a rewrite provider appears.

## What every profile obeys

- **Order**: `inspect → transform … → rewrite (at most one) → format → validate`.
- **At most one rewrite stage**, unless `extensions_cleaner_max_rewrite_stages` is raised — which is allowed and
  warned about.
- **No profile includes `metadata-attribution` or `c2pa`.** Those require a pipeline that names the stage and an
  invocation that names the file.
- **No profile requests a remote provider.** Refused at 1.0.

## `safe` is a profile name, not a guarantee

It means *deterministic, allowlisted, region-scoped and validated* — a description of the process, not a promise
about the result. Stripping invisible Unicode can still change behaviour through a string literal, a regex, a
fixture or a snapshot, all of which survive a successful parse. That is why `safe` escalates its validation on a
diff touching a runtime region instead of trusting its own name.
