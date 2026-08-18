---
schema: provider/1
id: watermarks-remover
version: 1
license: MIT
locality: local

type: cli
command: "${python}"
args:
  - "${workspace}/service/scripts/clean_text.py"
  - "${input}"
  - "-o"
  - "${output}"
  - "--stats"

operations:
  unicode:
    role: transform
    capability: unicode
    deterministic: true
    chainable: true
    regions: any
---

# watermarks-remover

Layer A of [watermarks-remover](https://github.com/guillaumemeyer/watermarks-remover): removes invisible
Unicode carriers — zero-width characters, bidi controls, tag characters — and normalises exotic spaces to
`U+0020`.

- **Licence**: MIT, read from the repository's `LICENSE` file on 2026-08-18.
- **Requires**: Python 3.10 or newer. **No third-party packages** — upstream is standard-library only for the
  core, the same constraint this runner works under.
- **Probed against**: v0.5.0, on 2026-08-18. The measurements are in the knowledge base, not here.

## Why only `unicode`

Upstream offers three layers. Only the first ships as a capability here, and each omission has a reason:

| Upstream | Why not in 1.0 |
|---|---|
| File cleaners — C2PA, EXIF, XMP, document properties | They **auto-use `exiftool`, `c2patool` and `qpdf` when present**, so the same command gives different results on different hosts. That is reproducible per host, which is not what `deterministic: true` claims |
| Layer B — statistical rewrite | Upstream ships no rewrite model: `--backend print-prompt` prints a prompt rather than rewriting, and the backends that do rewrite reach a network endpoint. Out of scope while 1.0 ships no remote provider |

Layer A has no such dependency, which is what makes it the one operation that can honestly declare
`deterministic: true`.

## Region handling

**This provider is not region-aware**, and it does not need to be. Given a whole source file it strips invisible
characters from string literals as readily as from comments — measured, not assumed.

So it is never given a whole file. The runner extracts the regions the stage's scope permits, sends only those,
and splices the result back; everything outside them is copied verbatim from the original. `regions: any` in the
declaration above means *this operation is willing to work on whatever it is handed* — the narrowing is the
pipeline's job, and `safe` hands it prose only.

## Behaviour worth knowing

| Aspect | Measured on v0.5.0 |
|---|---|
| Exit code | `0` on success, `1` on failure |
| Line endings | Preserved — CRLF stays CRLF |
| Trailing newline | Preserved, including its absence |
| No change | Output is byte-identical, and `--stats` reports `"removed": {}` |
| Report | `--stats` writes JSON to **stderr**, naming each removed codepoint: `"U+200B ZERO WIDTH SPACE (Cf)": 1` |

That report is better than a count, and the runner passes it through rather than restating it.

## Scope limits, stated upstream

Quoted rather than inferred, from the project's own skill documentation:

- *"Layer A does **not** remove token-sampling watermarks."*
- C2PA soft binding is out of scope.
- Data-driven and backdoor marks — trigger phrases — are out of scope.
- **Honest reporting is required: no claims of "undetectable" results.**

The last one is this extension's own rule arriving from the other direction: **removal is not proof of
absence.** Report what was removed, never what remains.

## Installation

Not installed by MEM, and never by an agent. Obtain it from upstream and record where it landed. `${workspace}`
in the argument vector resolves to the configured project root, so a project that keeps the checkout elsewhere
should pin an absolute path in a `custom/providers/` definition instead of editing this file — a base file is
replaced by the next update.

## Alternatives

None in this catalogue. The other projects named in the original plan — MarkLLM and `lm-watermarking` — are a
watermarking and evaluation toolkit and a generation-and-detection implementation respectively. Neither is a
general-purpose remover, and neither ships in 1.0.
