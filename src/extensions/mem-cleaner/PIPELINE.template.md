# Pipeline definition template

A pipeline is an ordered list of stages. A stage declares a **role** and a **capability**; which provider
satisfies it is configuration, not part of the pipeline.

Copy into `custom/pipelines/<id>.md`. The id is namespaced `custom/<id>` and may not shadow a distributed one.

```markdown
---
schema: pipeline/1
id: custom/<id>
version: 1

stages:
  - role: transform
    capability: unicode

  - role: transform
    capability: metadata-technical

  - role: validate
    builtin: syntax
---

# custom/<id>

What this pipeline is for, and when to prefer it over the shipped ones.
```

## Pinning a provider

A stage may name one explicitly:

```yaml
  - role: transform
    provider: custom/acme-tool
    capability: unicode
```

Legitimate when only one implementation will do — and the exception. A pin makes the pipeline non-portable by
choice rather than by accident, it is recorded, and it is disclosed on first use.

## Field rules

| Field | Rule |
|---|---|
| `role` | `inspect`, `transform` or `validate`. What the validator counts against the rewrite limit |
| `capability` | What the stage needs. Resolution to a provider happens at run time, from configuration |
| `regions` | `prose`, `runtime` or `any` (default). Which classified regions this stage may touch. **Checked at binding**: an operation is usable only if it touches the requested region, so a stage asking for `runtime` from a `prose`-only operation is refused rather than silently narrowed. The effective scope is the narrower of the two |
| `provider` | Optional pin. A stage with both `provider` and `capability` requires that provider to declare that capability |
| `builtin` | `syntax`, `format`, `project` — validation stages the runner performs itself |

## Order and limits

```text
inspect → transform … → rewrite (at most one) → format → validate
```

- Deterministic transforms chain freely.
- **At most `extensions_cleaner_max_rewrite_stages` rewrite stages**, default 1. Exceeding it makes the pipeline
  invalid, and it is refused before anything runs rather than failing partway.
- A rewrite stage requires full validation. A pipeline containing one and no `validate` stage is invalid.

## What a pipeline may not do

- Reach a `metadata-attribution` or `c2pa` capability without being invoked against an explicitly named target.
  These are excluded from every default pipeline and from wildcard automation.
- Request `locality: remote`. Refused at 1.0.
- Shadow a distributed id.

## Naming

`safe`, `balanced` and `full` are reserved for the shipped profiles. **`safe` names a profile, not a
guarantee**: deterministic, allowlisted, region-scoped and validated describes the process, not the result.
Choose a custom id that describes intent — `docs-only`, `pre-release` — rather than a reassurance.
