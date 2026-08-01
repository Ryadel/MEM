# Changelog

All notable MEM changes are documented in this file.

MEM uses `MAJOR.MINOR.BUILD` versioning. Version-to-version migration steps are documented in [MEM.upgrade.md](MEM.upgrade.md).

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

