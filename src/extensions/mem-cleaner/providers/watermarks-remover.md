---
schema: provider/1
id: watermarks-remover
version: 2
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

  rewrite:
    role: transform
    capability: statistical-rewrite
    deterministic: false
    chainable: false
    regions: prose
    args:
      - "${workspace}/service/scripts/rewrite_text.py"
      - "${input}"
      - "-o"
      - "${output}"
      - "--backend"
      - "ollama"
      - "--base-url"
      - "http://127.0.0.1:11434"
      - "--model"
      - "${model}"
      - "--strength"
      - "paraphrase"
      - "--temperature"
      - "0.3"
      - "--timeout"
      - "240"
      - "--json-stats"
---

# watermarks-remover

Layer A of [watermarks-remover](https://github.com/guillaumemeyer/watermarks-remover): removes invisible
Unicode carriers — zero-width characters, bidi controls, tag characters — and normalises exotic spaces to
`U+0020`.

- **Licence**: MIT, read from the repository's `LICENSE` file on 2026-08-18.
- **Requires**: Python 3.10 or newer. **No third-party packages** — upstream is standard-library only for the
  core, the same constraint this runner works under.
- **Probed against**: v0.5.0, on 2026-08-18. The measurements are in the knowledge base, not here.

## Two operations, two different promises

`unicode` deletes bytes and `rewrite` reformulates sentences. They share an upstream project and nothing else,
which is why the second carries its own argument vector: `clean_text.py` and `rewrite_text.py` are separate
programs, and pretending one vector fits both would have meant two provider ids for one tool.

| | `unicode` | `rewrite` |
|---|---|---|
| Capability | `unicode` | `statistical-rewrite` |
| Removes | invisible carriers, byte by byte | statistical marks, by rewording |
| `deterministic` | `true` | **`false`** |
| `chainable` | `true` | **`false`** — a second rewrite would compound the drift |
| Regions | `any`, narrowed by the pipeline | **`prose` in the definition**, so no pipeline can widen it |
| Needs | nothing beyond Python | a model on this host, and `extensions_cleaner_rewrite_model` naming it |
| Validation it forces | whatever its scope demands | **`tests`, always** — see below |

## Why only `unicode` in the default profile

Upstream offers three layers. Only the first ships in `safe`, and each omission has a reason:

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

## The rewrite operation

### It is local, and the definition is what makes that true

The vector pins `--backend ollama` and `--base-url http://127.0.0.1:11434`, and it never passes
`--allow-remote`. Upstream's other two backends are `print-prompt`, which prints a prompt instead of rewriting,
and `openai-compatible`, which is how the tool reaches an API. Neither belongs here at 1.0.

That is not left to good manners. The runner refuses, **at definition load**, any vector naming a non-loopback
host or passing `--allow-remote` — so a project that edits this file to point somewhere else gets a refusal
with the host named, not a run. Loopback is what keeps this inside the rule that no file content leaves the
machine: nothing crosses the network interface.

### The model is configuration, not definition

`${model}` is substituted from `extensions_cleaner_rewrite_model`. Which model a host has pulled is a fact
about that host, so a definition naming one would be wrong on every machine that chose differently. With no
model configured the stage **refuses and names the setting**; it does not fall back to a default, because a
rewrite by an unintended model is exactly the outcome worth refusing.

### Temperature 0.3, deliberately below upstream's 0.9

Upstream defaults high for candidate diversity, which suits a tool whose goal is to defeat a detector. The goal
here is a file the author still recognises, so the vector pins it low. The cost is stated rather than hidden: a
low temperature removes less of a statistical watermark. This profile prefers a faithful file over a thorough
scrub, and *"removal is not proof of absence"* applies with more force here than anywhere else in this
extension.

### Layer A runs on the model output, and that is left on

Upstream scrubs invisible Unicode from what the model returns unless `--no-layer-a-after` is passed. The flag
is not passed. A model can emit zero-width characters of its own, and catching them at the source is cheaper
than explaining them later.

### It always escalates validation to `tests`

A rewrite is bound to `regions: prose`, and for a deterministic stage that scope would demand only `syntax`.
That is not honest for a rewrite: reformulated prose parses perfectly. A docstring is reachable as `__doc__`
and executed by doctest, and a comment can carry a directive — both survive rewording without a syntax error
and with different behaviour. So the runner escalates on **determinism** rather than on region, and a
non-deterministic stage demands `tests` wherever it stayed.

A project with no test command therefore cannot run this stage at all. That is the intended answer: an
escalation that cannot be satisfied is a refusal, not a downgrade.

### It never runs unattended

`statistical-rewrite` is a restricted capability, so it requires an explicitly named target and never runs over
a session's record or a glob. Upstream states the reason better than this page could: rewriting *"flattens
tone, voice, and precision"* by substituting the model's word choices for the author's. That is an argument for
keeping it out of automatic mode permanently, not only until it is implemented.

## Installation

Not installed by MEM, and never by an agent. Obtain it from upstream and record where it landed. `${workspace}`
in the argument vector resolves to the configured project root, so a project that keeps the checkout elsewhere
should pin an absolute path in a `custom/providers/` definition instead of editing this file — a base file is
replaced by the next update.

## Alternatives

None in this catalogue. The other projects named in the original plan — MarkLLM and `lm-watermarking` — are a
watermarking and evaluation toolkit and a generation-and-detection implementation respectively. Neither is a
general-purpose remover, and neither ships in 1.0.
