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
- **executable content**: yes | no
- **default mode**: read-only | may-write
- **bootstrap entry**: <path under the extension's custom/, when it declares one>
- **summary**: one line
- **base files**:

```text
extensions/<extension-id>/index.md
extensions/<extension-id>/...
```
````

`provides` is what the agent matches against an unresolved command or an unmet capability. `base files` is the
exact update set for that extension.

`version` here is the **available** version. It is compared against the version declared in the installed
extension's base `index.md` — see `MEM.md`, "Checking extension versions". A gap is reported and may be
proposed; it never authorises an install on its own.

`bootstrap entry` is optional and declares a file the extension creates under its own `custom/` at installation.
It is **not** a base file and is never written by an update: listing it here only tells a reader it exists.

`executable content` declares whether any base file is **run** rather than read. It governs a separate approval:
installing or updating such an extension writes code into the consuming repository, and the confirmation must
name those files as executable. See `MEM.md`, "Instruction text and executable content". An extension declaring
`yes` is not proposed at all when `extensions_allow_executable_content` is false.

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

- **version**: 1.0.1
- **provides**: `TOOLS`, and the CLI capability registry
- **precedence**: custom
- **external actions**: no
- **default mode**: read-only
- **bootstrap entry**: `extensions/mem-toolbox/custom/installed/<host>.md`
- **summary**: which CLI tool to use for a task, and whether it is available on this host. Ships a small media
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
extensions/mem-toolbox/catalog/realesrgan.md
extensions/mem-toolbox/catalog/ffmpeg.md
```

- **removed in 1.0.1**: `extensions/mem-toolbox/catalog/realesrgan-ncnn-vulkan.md`, renamed to
  `realesrgan.md`. An update writes the listed paths and **never deletes**, so an installation upgraded from
  1.0.0 keeps the old file until it is removed by hand. `MEM.upgrade.md` states this.

Nothing under `extensions/mem-toolbox/custom/` is listed here, so project entries and per-host data survive every
update — including the bootstrap entry, which the extension creates rather than the manifest.
