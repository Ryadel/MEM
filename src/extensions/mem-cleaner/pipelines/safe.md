---
schema: pipeline/1
id: safe
version: 1

stages:
  - role: transform
    capability: unicode
    regions: prose

  - role: validate
    builtin: syntax
---

# `safe`

The default profile: one deterministic transformation, applied only to prose regions, validated before anything
is replaced. No rewrite stage, so nothing here reformulates content.

## Why there is no metadata stage

An earlier draft had one. `metadata-technical` was dropped from 1.0 when the first provider was measured:
upstream **auto-uses `exiftool`, `c2patool` and `qpdf` when they happen to be installed**, so the same command
produces different results on different machines. That is reproducible per host, which is not what
`deterministic: true` claims — and `deterministic` is precisely what excuses a stage from full validation.

`unicode` carries no such dependency, which is why it is the one operation in the default profile.

## The name is a profile, not a guarantee

`safe` means *deterministic, allowlisted, region-scoped and validated*. That describes the process. It does not
promise the result is semantically identical, and treating it as though it did is the mistake this page exists
to prevent.

Stripping invisible Unicode can change behaviour through a string literal, a regular expression, a test fixture
or a snapshot — and every one of those survives a successful parse. A snapshot assertion compares bytes, so a
"harmless" normalisation breaks it while the file compiles perfectly.

Hence the escalation rule below, which is not a formality.

## Region scope

The `unicode` stage is restricted to `regions: prose`. It never touches:

- **directives** — `# type: ignore`, `# pragma`, `# noqa`, `eslint-disable`, `// @ts-ignore`, `//go:build`,
  annotation processors. A byte change there alters compilation, linting or generation;
- **runtime regions** — docstrings, which are reachable as `__doc__` and executed by doctest, plus literals,
  regexes, fixtures, golden files and snapshots.

**Doubt escalates**: an unclassifiable region is treated as runtime, never as prose.

The `metadata-technical` stage removes only fields the provider enumerates in its allowlist. A wildcard is
refused, which is what stops a provider gaining a broader stripping mode upstream from silently widening this
profile.

## Validation

Parse and formatter are unconditional. If the diff touches a runtime region, validation **escalates** to the
project's test command.

An escalation that cannot be satisfied — no test command configured — is a **refusal, not a downgrade**: under
`automatic` the transformation is skipped and reported, and under an explicit `MEM CLEAN` the reduced guarantee
is stated and the user is asked.

## What this profile never does

- Reformulate content. There is no rewrite stage.
- Touch `metadata-attribution` or `c2pa`. Those need a pipeline naming the stage and an invocation naming the
  file.
- Reach a remote provider.
