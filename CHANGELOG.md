# Changelog

All notable MEM changes are documented in this file.

MEM uses `MAJOR.MINOR.BUILD` versioning. Version-to-version migration steps are documented in [MEM.upgrade.md](MEM.upgrade.md).

## 1.1.4 - 2026-08-17

### Added

- Added **executable content** as a declared, separately approved kind of extension file. An extension whose
  base files are *run* rather than read declares `executable content: yes`; installing or updating it requires
  approval naming those files as executable, and `extensions_allow_executable_content` — default `false` —
  gates it entirely.
- Added `extensions_allow_executable_content: false`.
- Added **subcommands** to the command grammar: `MEM <COMMAND> [<SUBCOMMAND>] [target]`. An extension declares a
  closed set in its base `index.md`; a token outside that set is a target, and a target beginning with `./` is
  always a target. Core commands declare none, and an extension may not add one to a core command.
- Added a naming rule for extension configuration options: `extensions_<id>_<option>`, so a project-authored
  extension cannot collide with a future core option.
- Added extension version checking. Every `MEM.md` update now also compares each installed extension's declared
  version against the version the manifest offers, and reports the gap in the daily log and in `MEM STATUS`.
- Added `extensions_check_updates: true`, which governs that check.
- Added the **bootstrap entry**: an extension may declare one file under its own `custom/` that is created at
  installation rather than on first write. It is the single exception to "an absent `custom/` is normal".
- Added `ffmpeg` to the `mem-toolbox` catalogue, with transcoding, frame extraction, audio-track work and media
  inspection. The catalogue's scope widens from image processing to media processing.
- Added a tools-directory convention to `mem-toolbox`: `<tool-id>/<version>[-<variant>][-<target>]/`, so the
  tool name is what you scan for and several builds of one tool coexist.

### Changed

- `mem-toolbox` is now 1.0.1. Its per-host file `custom/installed/<host>.md` is its bootstrap entry: created at
  installation with host, OS and tools root, before any tool has been probed.
- `mem-toolbox` now asks two questions at installation and records both in the host file: **where portable tools
  live on this host** (`tools root`, never guessed, `none` a valid answer) and whether `custom/installed/` is
  kept under source control. The source-control default is unchanged — yes, committed — but it is now an
  explicit question rather than a silent default.
- Knowing the tools root lets an installation proposal name the exact directory an archive should be unpacked
  into, instead of only naming a tool. It remains a sentence in a proposal: the agent still never downloads,
  unpacks, moves or deletes anything under that root.
- Renamed the catalogue entry `realesrgan-ncnn-vulkan` to `realesrgan`. The id names the tool; `ncnn-vulkan` is
  one implementation of it and belongs to the build path, not to the catalogue id.
- The installed-entry schema gains `tools root` and `source control`, and `version` now explicitly means the
  version the tool *reported*, not the one written on its folder.
- `EXT.md`'s `version` is now formally a copy: an extension's base `index.md` is authoritative when the two
  disagree.

### Compatibility

- **The definition of an extension changed.** "An extension is stored instruction text… it must not grant
  itself permissions that `MEM.config.md` denies" now applies to instruction text only, and says so. For
  executable content the specification states plainly that there is no enforcement point, and replaces the
  guarantee with a review obligation: such content must be small enough to review. Extending the old sentence
  to cover code would have left a promise nothing could keep.
- Executable content is delivered **into the consuming repository**, so an extension update arrives as a
  reviewable diff rather than an opaque package version. That is the property the mechanism trades for.
- Projects that do not set `extensions_allow_executable_content: true` see no change: no such extension is
  proposed, and none is run.
- Subcommands are **positional and command-scoped**, unlike `MEM FORCE`, which remains a modifier applying to
  the whole request regardless of position. The two mechanisms are distinct and the terms are not synonyms.
- The grammar change is backwards compatible: a command with no declared subcommands parses exactly as before,
  and every existing invocation keeps its meaning.
- The version check **reports and proposes; it never installs**. A version gap is not authorization, for the
  same reason that being listed in the manifest is not authorization.
- An extension absent from the manifest is reported as *unchecked*, never as outdated. If the manifest cannot be
  fetched, MEM says versions could not be checked rather than assuming they are current.
- `extensions_enabled: false` suppresses the check entirely.
- One configuration option was added; none was removed or renamed.
- Renaming a catalogue entry is a file rename in a base layer, and an update **writes** the manifest paths
  without deleting anything. Installations upgrading from 1.1.3 keep the orphaned
  `catalog/realesrgan-ncnn-vulkan.md` until it is removed by hand. See `MEM.upgrade.md`.

## 1.1.3 - 2026-08-01

### Added

- Added the `mem-toolbox` extension: which CLI tool to use for a task, and whether it is available on the current
  host.
- Added `MEM TOOLS`, read-only, listing known tools with their capability, availability, and stale verifications.
- Added `TOOL.template.md`, with separate schemas for a portable catalogue entry and a per-host installed entry.
- Added an initial catalogue scoped to image processing: ImageMagick, vips, oxipng, resvg, and
  realesrgan-ncnn-vulkan, each with its licence read from upstream and dated.

### Changed

- The manifest carries a second entry, so an unresolved capability can lead to an installation proposal.

### Compatibility

- Availability is recorded per host, never inside a catalogue entry, so a shared knowledge base cannot make an
  agent on another machine assume a tool is present and skip asking.
- Per-host files are written automatically because they record an observation; catalogue entries require
  confirmation because they are an editorial judgement.
- Precedence is **custom wins**, the opposite of `mem-commands`, and the override is disclosed on first use.
- The agent never installs a tool: entries carry URLs, never install commands.
- No configuration options were added, removed, or renamed.

## 1.1.2 - 2026-08-01

### Added

- Added the `mem-commands` extension, the first entry in the manifest.
- Added `MEM REVIEW <target>`: assesses a plan, task, or troubleshooting document before or independently of its
  implementation, without treating unbuilt work as a defect.
- Added `MEM CHECK <target>`: assumes the work was declared complete and verifies it against the implementation
  that exists, including the diff, the source, and build and test outcomes.
- Added `MEM DEFINE <COMMAND>`: authors a project-specific command from `COMMAND.template.md` into
  `custom/`, the extension's only writing operation.
- Added `COMMAND.template.md`, the definition schema, with `mode`, `shell`, and `external` as permission fields.
- Added a shared procedure for the review commands: target resolution, evidence labelling, four severity levels,
  five verdicts with a fixed precedence, and a fixed report layout.

### Changed

- The manifest now carries its first catalogue entry, so an unresolved `REVIEW`, `CHECK`, or `DEFINE` leads to an
  installation proposal rather than a dead end.

### Compatibility

- `REVIEW` and `CHECK` are read-only: they never modify code, change an item's status, move files, or commit.
  Reports are returned in the conversation and persisted only on request.
- `CHECK` runs only build and test commands explicitly configured in `MEM.config.md`, never auto-detected ones,
  and subject to `extensions_require_confirmation`. Anything not run is reported as `Unverified`.
- `DEFINE` writes only under `extensions/mem-commands/custom/`, with confirmation.
- No configuration options were added, removed, or renamed.

## 1.1.1 - 2026-08-01

### Added

- Added the extension manifest at `src/extensions/manifest.md`: which extensions MEM distributes, what each
  provides, and the exact file list of each base layer.
- Added `src/extensions/EXT.index.template.md`, the registration template the knowledge base structure has
  referenced since 1.0.4.
- Added the authorization model: the manifest governs what may be **proposed**, while an extension is loaded
  only when its files are present locally and it is registered `active` in `EXT.md`.
- Added the approval / disclosure boundary. Acquiring or mutating — installing, writing files, external actions,
  running commands — requires explicit approval. Using an extension already registered `active` requires
  disclosure on the acknowledgement line instead, since registration is the approval.
- Added the installation proposal: proposed at most once per session, never performed unprompted, confirmed with
  the file list and the source URL, and recorded as `status: declined` when refused.

### Changed

- The manifest is now the update set: an update writes only the paths it lists, so `custom/` folders and
  `EXT.md` are project-owned by construction.
- Manifest paths are relative to `KB_ROOT` and must not hardcode a folder name such as `MEM/`.
- Updating `MEM.md` no longer implies updating extensions: `mem_update_url` carries `MEM.md` alone.
- An extension not listed in the manifest discloses its provenance the first time it is used in a session.

### Configuration

- Added `mem_manifest_url`.

### Compatibility

- Installation is still a single `MEM.md`. Extensions are installed on demand, with confirmation.
- With `extensions_enabled: false`, no installation is ever proposed.

## 1.1.0 - 2026-08-01

### Added

- Added reserved commands: the grammar `MEM <COMMAND> [target]`, activation and non-activation rules, the
  acknowledgement line, the resolution order, and the dispatch table covering unknown, absent, disabled, and
  broken-registration cases.
- Added the core commands `MEM HELP`, `MEM STATUS`, `MEM INIT`, `MEM UPDATE`, `MEM LINT`, and `MEM FORCE`.
- Added the base / custom layer pattern for extensions, including the requirement that each extension declare
  its own precedence and point to `custom/index.md`.
- Added a required registration schema for entries in `extensions/EXT.md`.

### Changed

- `extensions/EXT.md` is now read at session start when extensions are enabled, because it is the routing table
  for reserved commands.
- The knowledge base structure shows `custom/` inside an extension folder.
- Extension updates replace base-layer files only; deleting and reinstalling an extension folder is forbidden.

### Compatibility

- Prompts containing no reserved command behave exactly as in 1.0.4.
- No configuration options were added, removed, or renamed.
- Installation is unchanged: a single `MEM.md` file.
- 1.0.4 is the earliest documented upgrade baseline.

## 1.0.4 - 2026-04-30

### Added

- Added `CHANGELOG.md` for human-readable release notes.
- Added `MEM.upgrade.md` for sequential version-to-version upgrade instructions.
- Added the `mem_upgrade_url` configuration option.
- Added MEM update guidance requiring agents to check upgrade notes after successful updates.

### Changed

- Reworked dynamic item management for `tasks/` and `troubleshooting/`.
- Introduced `index.md`, `current/`, and `done/` under dynamic areas.
- Reframed `archive/` as a place for obsolete or superseded knowledge, not ordinary completed work.
- Renamed "Operational Extensions" to "Extensions" in user-facing MEM documentation.
- Renamed extension-related configuration options so they share the `extensions_` prefix.
- Simplified extension confirmation configuration to `extensions_require_confirmation`.
- Renamed extension "external side effects" wording to "external actions" in documentation.
- Linked the changelog and upgrade guide from `README.md`.
- Updated `README.md` examples to match the `tasks/current/`, `tasks/done/`, `troubleshooting/current/`, and `troubleshooting/done/` structure.
- Updated routing, end-of-session checks, linting checks, and first-time initialization paths.

### Configuration

- Added `mem_upgrade_url`.
- Removed `auto_archive_completed_items`; use the area-specific options instead.
- Replaced `archive_completed_tasks` with `move_completed_tasks_to_done`.
- Replaced `archive_resolved_oneoff_troubleshooting` with `move_completed_troubleshooting_to_done`.
- Replaced `enable_operational_extensions` with `extensions_enabled`.
- Replaced `allow_extension_external_side_effects` with `extensions_allow_external_side_effects`.
- Replaced `require_confirmation_for_extension_side_effects` with `extensions_require_confirmation`.

