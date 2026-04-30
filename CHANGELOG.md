# Changelog

All notable MEM changes are documented in this file.

MEM uses `MAJOR.MINOR.BUILD` versioning. Version-to-version migration steps are documented in [MEM.upgrade.md](MEM.upgrade.md).

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

