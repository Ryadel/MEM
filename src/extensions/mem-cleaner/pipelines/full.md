---
schema: pipeline/1
id: full
version: 1

stages:
  - role: transform
    capability: unicode
    regions: prose

  - role: transform
    capability: statistical-rewrite
    regions: prose

  - role: validate
    builtin: syntax
---

# `full`

The profile `MEM CLEAN FULL <target>` selects. It is [`safe`](safe.md) plus one rewrite stage, and everything
that follows is about what that one stage costs.

Deterministic cleaning runs first. Deleting invisible characters before rewording means the model is handed
text without carriers in it, so it cannot copy one into its output — and the same operation running afterwards
would have to be trusted not to have introduced any.

## What the rewrite stage is for

`unicode` removes marks that are *carried* by a file: zero-width characters, bidi controls, tag characters.
Delete the bytes and the mark is gone.

A statistical watermark is not carried anywhere. It is a bias in **which words were chosen**, spread across the
whole text, and no byte can be deleted to remove it. The only way to disturb it is to say the same thing with
different words — which is why this stage exists and why it cannot be deterministic.

## Everything this profile does not promise

`safe` warns that its name describes a process rather than a result. That warning applies here several times
over.

- **The text is reworded.** Tone, voice and precision are the author's; a rewrite substitutes the model's.
  Upstream says so in its own documentation, and this profile does not argue with it.
- **The result is not reproducible.** Two runs over the same file give two different files. That is what
  `deterministic: false` means, and it is why nothing here may run unattended.
- **Removal is not proof of absence.** A watermark that survives the rewording is still there, and this
  extension has no way to tell you it is. No run of this profile licenses a claim that a file is clean.

## Why it cannot run unattended, by mechanism

Three independent rules apply, and each would be enough on its own:

| Rule | Where it lives | Effect |
|---|---|---|
| `statistical-rewrite` is a restricted capability | the pipeline validator | refuses to run without an explicitly named target, so never over a session's record or a glob |
| A non-deterministic stage demands validation at `tests` | the runner's escalation | a project with no test command cannot run this profile at all |
| At most one rewrite stage | `extensions_cleaner_max_rewrite_stages`, default 1 | a second one is refused by name, so the drift cannot be compounded |

None of the three is documentation asking nicely. Each is enforced where the pipeline is resolved.

## What it needs before it will run

- `extensions_cleaner_rewrite_model`, naming a model this host has. There is no default: the stage refuses and
  names the setting rather than guessing which model you meant.
- A model reachable on loopback. The provider vector pins `--backend ollama` at `127.0.0.1`, and a definition
  pointing anywhere else is refused when it is read.
- `test_command` in `MEM.config.md`, because the escalation to `tests` is unconditional here.

Missing any of the three is a refusal that names what is missing. None of them degrades to a weaker run.
