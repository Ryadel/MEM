# Pipelines

Two profiles ship. `extensions_cleaner_pipeline` selects the one used by default; `MEM CLEAN SAFE` and
`MEM CLEAN FULL` name one explicitly, and a project may add its own under `custom/pipelines/`.

| Profile | Stages | Rewrite stages | Validation |
|---|---|---|---|
| [`safe`](safe.md) | `unicode` over prose regions, then a syntax check | 0 | Parse; escalates on a runtime-region change |
| [`full`](full.md) | `safe`, plus one `statistical-rewrite` stage over prose regions | 1 | **Always `tests`** — a non-deterministic stage escalates on determinism, not on region |
| `balanced` | not shipped | — | — |

**`safe` is the default and the only profile that can run unattended.** `full` requires an explicitly named
target, a configured `test_command` and a model on this host; missing any of the three is a refusal that names
what is missing.

`balanced` is not shipped because nothing has needed a third point between the two: `safe` is what runs by
default, and `full` is a deliberate act. Inventing a middle profile would mean inventing the judgement that
picks it.

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
