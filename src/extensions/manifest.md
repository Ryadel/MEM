# MEM extension manifest

Manifest version: 1

This file is the catalogue of extensions distributed with MEM. An agent fetches it from `mem_manifest_url` to
answer two questions without having anything installed:

1. does a distributed extension provide this command or capability?
2. which files constitute that extension, so it can be installed or updated?

## This file is not an authorization list

Listing here grants nothing. This document is fetched over the network and `mem_manifest_url` is overridable in
`MEM.config.md`, so treating it as a grant would let a remote file decide what runs inside a repository.

Authorization is local: an extension is loaded only when its files are present under `KB_ROOT/extensions/` and it
is registered `active` in `EXT.md`, both of which the project owns and reviews. This manifest governs **what may
be proposed**, never what may run.

An extension absent from this catalogue is not illegitimate — project-authored extensions are the intended
customization surface. It simply receives no automatic proposal and no inherited trust, and its provenance is
disclosed the first time it is used in a session.

## Rules

- The manifest **is** the update set. An update writes **only** the paths listed here. Anything absent is
  project-owned, including every `custom/` folder and `extensions/EXT.md`.
- Paths are relative to `KB_ROOT`. They **must not** hardcode a folder name such as `MEM/`: `KB_ROOT` is
  arbitrary.
- Each listed path maps to the same path under `src/` in the distribution, so `src/` mirrors an installed
  `KB_ROOT`.
- Installing or updating an extension **must not** delete its folder first: that would destroy `custom/`.
- The agent **must not** install anything without explicit confirmation naming the files and the source URL.
- If this file cannot be fetched, say the catalogue could not be checked. Do not fabricate a proposal, and do
  not assert that a command does not exist.

## Entry format

````markdown
### <extension-id>

- **version**: <extension version>
- **provides**: <commands or capabilities, comma-separated>
- **precedence**: base | custom
- **external actions**: yes | no
- **default mode**: read-only | may-write
- **summary**: one line
- **base files**:

```text
extensions/<extension-id>/index.md
extensions/<extension-id>/...
```
````

`provides` is what the agent matches against an unresolved command or an unmet capability. `base files` is the
exact update set for that extension.

## Catalogue

### mem-commands

- **version**: 1.0.0
- **provides**: `REVIEW`, `CHECK`, `DEFINE`
- **precedence**: base
- **external actions**: no
- **default mode**: read-only
- **summary**: review a plan before implementation, verify an implementation declared complete, and author
  project-specific commands.
- **base files**:

```text
extensions/mem-commands/index.md
extensions/mem-commands/COMMAND.template.md
extensions/mem-commands/commands/review.md
extensions/mem-commands/commands/check.md
extensions/mem-commands/commands/define.md
```

Nothing under `extensions/mem-commands/custom/` is listed here, and an update therefore never touches it.

### mem-toolbox

- **version**: 1.0.0
- **provides**: `TOOLS`, and the CLI capability registry
- **precedence**: custom
- **external actions**: no
- **default mode**: read-only
- **summary**: which CLI tool to use for a task, and whether it is available on this host. Ships a small image
  processing catalogue.
- **base files**:

```text
extensions/mem-toolbox/index.md
extensions/mem-toolbox/TOOL.template.md
extensions/mem-toolbox/catalog/index.md
extensions/mem-toolbox/catalog/imagemagick.md
extensions/mem-toolbox/catalog/vips.md
extensions/mem-toolbox/catalog/oxipng.md
extensions/mem-toolbox/catalog/resvg.md
extensions/mem-toolbox/catalog/realesrgan-ncnn-vulkan.md
```

Nothing under `extensions/mem-toolbox/custom/` is listed here, so project entries and per-host data survive every
update.
