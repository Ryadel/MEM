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
`yes` is not proposed when `extensions_allow_executable_content` is false, except in the catalogue offer, which
lists it as needing that setting — see `MEM.md`, "Offering the catalogue".

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

- **version**: 1.0.3
- **provides**: `TOOLS` (subcommands `CHECK`, `SETUP`), and the tool, library and runtime capability registry
- **precedence**: custom
- **external actions**: yes — the machine file `~/.mem/mem-toolbox/host.md` once confirmed, and approved package
  installs into a dedicated agent environment
- **executable content**: no
- **default mode**: read-only
- **summary**: which CLI tool or library to use for a task, and whether it is available on this host, recorded
  once per machine in `~/.mem/mem-toolbox/`. Ships a catalogue for media, documents and data, with the Python and
  Node runtimes libraries need.
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
extensions/mem-toolbox/catalog/index.media.md
extensions/mem-toolbox/catalog/index.documents.md
extensions/mem-toolbox/catalog/index.data.md
extensions/mem-toolbox/catalog/python.md
extensions/mem-toolbox/catalog/node.md
extensions/mem-toolbox/catalog/pillow.md
extensions/mem-toolbox/catalog/svgo.md
extensions/mem-toolbox/catalog/exiftool.md
extensions/mem-toolbox/catalog/reportlab.md
extensions/mem-toolbox/catalog/pypdf.md
extensions/mem-toolbox/catalog/pdfplumber.md
extensions/mem-toolbox/catalog/qpdf.md
extensions/mem-toolbox/catalog/pandoc.md
extensions/mem-toolbox/catalog/typst.md
extensions/mem-toolbox/catalog/python-docx.md
extensions/mem-toolbox/catalog/openpyxl.md
extensions/mem-toolbox/catalog/python-pptx.md
extensions/mem-toolbox/catalog/pandas.md
extensions/mem-toolbox/catalog/duckdb.md
extensions/mem-toolbox/catalog/jq.md
extensions/mem-toolbox/catalog/matplotlib.md
```

- **removed in 1.0.1**: `extensions/mem-toolbox/catalog/realesrgan-ncnn-vulkan.md`, renamed to
  `realesrgan.md`. An update writes the listed paths and **never deletes**, so an installation upgraded from
  1.0.0 keeps the old file until it is removed by hand. `MEM.upgrade.md` states this.

Nothing under `extensions/mem-toolbox/custom/` is listed here, so project entries and the optional copy of host
data survive every update. The machine file is outside the knowledge base and is never written by an update.

### mem-workspace

- **version**: 1.0.0
- **provides**: `WORKSPACE` (subcommands `CHECK`, `INIT`), and routing of files and commits across the
  repositories of a workspace
- **precedence**: base
- **external actions**: no
- **executable content**: no
- **default mode**: read-only
- **bootstrap entry**: `extensions/mem-workspace/custom/workspace.md`
- **summary**: keep the knowledge base in a private repository beside a public one, check that nothing private
  reaches the public side, and track commits across the repositories.
- **base files**:

```text
extensions/mem-workspace/index.md
extensions/mem-workspace/check.md
extensions/mem-workspace/setup.md
extensions/mem-workspace/WORKSPACE.template.md
extensions/mem-workspace/adapters/visual-studio.md
extensions/mem-workspace/adapters/vscode.md
```

Nothing under `extensions/mem-workspace/custom/` is listed here, so the workspace description survives every
update.

### mem-stats

- **version**: 0.1.1
- **provides**: `STATS` (subcommands `SETUP`, `STATUS`, `RESET`, `REPORT`, `WATCH`, `INGEST`, `PRUNE`, `INIT`,
  `INVENTORY`, `READ`), and usage measurement for Claude Code and Codex
- **precedence**: base
- **external actions**: no
- **executable content**: yes — `runner/stats.py`, `runner/claude_code.py`, `runner/codex.py`,
  `runner/hook_ingest.py`, `runner/setup.py` (Python 3.11+, standard library; 3.14+ to read Codex rollouts older
  than a week)
- **default mode**: may-write (settings files, only after the user confirms the plan)
- **summary**: measure what agent sessions consume, from the client's local logs — tokens per request, cache
  reads and rewrites, what fills the context (MEM included), compactions — per project and host-wide, into one
  local ledger of counts per user, filled automatically by a hook installed by a setup wizard.
- **base files**:

```text
extensions/mem-stats/index.md
extensions/mem-stats/runner/stats.py
extensions/mem-stats/runner/claude_code.py
extensions/mem-stats/runner/codex.py
extensions/mem-stats/runner/hook_ingest.py
extensions/mem-stats/runner/setup.py
extensions/mem-stats/prices/anthropic-api-2026-10-15.json
```

Project price cards live under `extensions/mem-stats/custom/`, never listed here. The ledger is outside the
repository, in `~/.mem/mem-stats/state/`.

### mem-optimize

- **version**: 0.3.1
- **provides**: `OPTIMIZE` (subcommands `SETUP`, `STATUS`, `RESET`, `PAGES`), and context-lifecycle hooks for
  Claude Code, Codex, Factory Droid, Qwen Code, OpenCode and Kilo Code
- **precedence**: base
- **external actions**: no
- **executable content**: yes — `runner/hook_prompt.py`, `runner/hook_session.py`, `runner/clients.py`,
  `runner/resume.py`, `runner/wizard.py`, `runner/pages.py` (Python 3.11+, standard library),
  `runner/opencode-plugin.js` (OpenCode plugin template)
- **default mode**: may-write
- **summary**: keep long sessions from wasting tokens — advice when a restart pays, a guided restart that carries
  the work over, the last exchanges restored after every `/clear`, a stop before a prompt rewrites an expired cache,
  re-orientation after a compaction, and the knowledge base pages worth lightening; installed by a setup wizard.
- **base files**:

```text
extensions/mem-optimize/index.md
extensions/mem-optimize/runner/hook_prompt.py
extensions/mem-optimize/runner/hook_session.py
extensions/mem-optimize/runner/clients.py
extensions/mem-optimize/runner/resume.py
extensions/mem-optimize/runner/wizard.py
extensions/mem-optimize/runner/pages.py
extensions/mem-optimize/runner/opencode-plugin.js
```

The project scope's setup log, settings backups and runtime state live under `extensions/mem-optimize/custom/`,
never listed here; the runtime state folder carries its own `.gitignore`. The user scope's live outside the repository,
in `~/.mem/mem-optimize/`.
