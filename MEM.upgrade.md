# MEM Upgrade Guide

This file describes operational steps for upgrading an existing MEM knowledge base from one MEM version to another.

## Upgrade Order

Apply upgrades sequentially, one version step at a time, in ascending version order.

For MEM versions using `MAJOR.MINOR.BUILD`:

1. apply all missing BUILD upgrades within the current MINOR;
2. then apply each missing MINOR upgrade in order;
3. then apply MAJOR upgrades in order.

Do not skip intermediate upgrade notes unless the target upgrade explicitly says it supersedes earlier steps.

Before applying an upgrade, identify the current local MEM version and the target MEM version. After applying an upgrade, update links and indexes touched by the migration.

## 1.0.3 -> 1.0.4

### Summary

Introduces dynamic `current/` and `done/` folders for tasks and troubleshooting, narrows `archive/` to obsolete or superseded knowledge, adds release/upgrade documentation, and simplifies extension configuration.

### Required actions

- Create `tasks/index.md` if missing.
- Create `tasks/current/` and `tasks/done/` if missing.
- Move open task files to `tasks/current/`.
- Move closed task files to `tasks/done/`.
- Create `troubleshooting/index.md` if missing.
- Create `troubleshooting/current/` and `troubleshooting/done/` if missing.
- Move active or recurring troubleshooting files to `troubleshooting/current/`.
- Move closed troubleshooting files to `troubleshooting/done/`.
- Update `tasks/index.md` and `troubleshooting/index.md` with concise links grouped by status.
- Update `MEM.index.md` links that pointed to moved files.
- Add or update `CHANGELOG.md` and `MEM.upgrade.md` when maintaining the MEM source distribution.
- Link `CHANGELOG.md` and `MEM.upgrade.md` from `README.md` when the repository exposes MEM documentation to humans.
- Replace "Operational Extensions" with "Extensions" in project-specific MEM documentation where it refers to MEM extension modules.
- Replace "external side effects" wording with "external actions" in project-specific MEM documentation where appropriate.

### Configuration changes

- Add `mem_upgrade_url` if the project needs to override the default upgrade guide location.
- Remove `auto_archive_completed_items`; use the area-specific options instead.
- Replace `archive_completed_tasks` with `move_completed_tasks_to_done`.
- Replace `archive_resolved_oneoff_troubleshooting` with `move_completed_troubleshooting_to_done`.
- Replace `enable_operational_extensions` with `extensions_enabled`.
- Replace `allow_extension_external_side_effects` with `extensions_allow_external_side_effects`.
- Replace `require_confirmation_for_extension_side_effects` with `extensions_require_confirmation`.

### Archive cleanup

- Keep ordinary completed tasks in `tasks/done/`.
- Keep ordinary resolved troubleshooting entries in `troubleshooting/done/`.
- Reserve `archive/` for obsolete, superseded, or no-longer-operational knowledge.

### Verification

- No open task remains only under `tasks/`.
- No active troubleshooting note remains only under `troubleshooting/`.
- `tasks/index.md` and `troubleshooting/index.md` list current and done items.
- `archive/` does not contain ordinary task history or troubleshooting history unless it is truly obsolete.
- `README.md` links to `CHANGELOG.md` and `MEM.upgrade.md`.
- `MEM.md` contains `mem_upgrade_url`.
- `MEM.md` instructs agents to check upgrade notes after successful updates.
- `MEM.config.md` does not contain the removed or replaced configuration names.
- Extension options appear together under the `extensions_` prefix.
- External actions still require explicit confirmation unless explicitly allowed by project configuration.

