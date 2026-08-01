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

_No extensions are published yet._

The mechanism ships ahead of its first entry, so an agent fetching this file gets a definite answer — "nothing
distributed provides that" — instead of an unreachable catalogue, which is a different situation requiring a
different message.
