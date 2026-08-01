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

## Documented baseline

**1.0.4 is the earliest documented baseline.** Upgrade notes exist from 1.0.3 onwards; there are none for
1.0.0 through 1.0.2. A knowledge base on a base earlier than 1.0.3 should be re-initialized against the current
MEM version rather than migrated step by step.

## 1.1.1 -> 1.1.2

### Summary

Publishes the `mem-commands` extension, providing `REVIEW`, `CHECK`, and `DEFINE`. Nothing is installed
automatically: the extension is offered when one of its commands is used, and installed only on confirmation.

### Required actions

- Replace `MEM.md` with version 1.1.2.
- No installation is required. If the project wants the commands, accept the proposal raised on first use, or
  install the base files listed in the manifest entry for `mem-commands`.
- If installed, register it in `EXT.md` with `status: active`, its version, and the triggers `REVIEW`, `CHECK`,
  `DEFINE`.
- Treat `REVIEW`, `CHECK`, and `DEFINE` as reserved: an existing project command using one of those names must be
  renamed, since a custom command cannot shadow a base one.
- To let `CHECK` verify build and test outcomes, set `build_command` and `test_command` explicitly in
  `MEM.config.md`. Auto-detected values are never executed.

### Configuration changes

None.

### Verification

- `MEM.md` reports version 1.1.2.
- `MEM HELP` lists `REVIEW`, `CHECK`, and `DEFINE` once the extension is installed.
- `MEM REVIEW` on a plan does not report unimplemented work as a defect.
- `MEM CHECK` reports build and test as `Unverified` when no command is configured, and never claims a success it
  did not observe.
- A missing or ambiguous target produces `BLOCKED` with the candidates listed.
- Neither `REVIEW` nor `CHECK` modifies a file, changes an item status, or creates a commit.
- `DEFINE` writes only under `extensions/mem-commands/custom/`, after confirmation.
- A custom command named `REVIEW`, `CHECK`, or `DEFINE` is refused, with the collision reported.
- An update of the extension leaves `custom/` untouched.

## 1.1.0 -> 1.1.1

### Summary

Adds the extension manifest and the rules built on it: the update set, the installation proposal, and an
authorization model that keeps the decision about what may run inside the repository rather than in a remote
file.

### Required actions

- Replace `MEM.md` with version 1.1.1.
- Treat the manifest as the update set: when updating an extension, write only the paths it lists, and never
  delete an extension folder to reinstall it.
- Verify that no local manifest or install routine hardcodes a folder name such as `MEM/`; paths are relative
  to `KB_ROOT`.
- Confirm every registered extension is present locally and marked `status: active` in `EXT.md`. An extension
  whose files are missing is a broken registration, not an installed extension.
- Record any refused installation as `status: declined` in `EXT.md` rather than re-proposing it.
- Where a project document instructs an agent to fetch extension files from somewhere other than the URL
  declared in `MEM.md`, make that source explicit so it can be shown at confirmation time.

### Configuration changes

- Add `mem_manifest_url` if the project needs to override the default catalogue location. Its default is
  `https://raw.githubusercontent.com/Ryadel/MEM/main/src/extensions/manifest.md`.

### Verification

- `MEM.md` reports version 1.1.1 and contains `mem_manifest_url`.
- An unresolved command leads to a proposal only when the manifest declares an extension providing it.
- No installation happens without a confirmation naming the files and the source URL.
- A declined proposal is not raised again in a later session.
- With `extensions_enabled: false`, nothing is proposed.
- An unreachable manifest is reported as such, without a fabricated proposal and without asserting that a
  command does not exist.
- An extension outside the manifest still works once registered, and discloses its provenance on first use.

## 1.0.4 -> 1.1.0

### Summary

Introduces reserved commands (`MEM <COMMAND>`), a set of core commands available without any extension, and the
base / custom layer pattern that every extension follows. No configuration changes, and no change to how MEM is
installed.

### Required actions

- Replace `MEM.md` with version 1.1.0.
- Read `extensions/EXT.md` at session start when `extensions_enabled` is true.
- If `extensions/EXT.md` exists, bring each entry up to the registration schema: `id`, `path`, `status`,
  `version`, `triggers`, a one-line description, whether it performs external actions, and its default mode.
  Amend the file; do not overwrite it.
- If an existing extension carries project-specific content mixed into its shipped files, move that content
  under `<extension-id>/custom/` and add `custom/index.md`.
- State each extension's precedence — base wins or custom wins — in its base `index.md`.
- Add a pointer from each extension's base `index.md` to its `custom/index.md`.
- Do not create `custom/` in extensions that have no project-specific content: its absence is a valid state.
- Check that no project documentation invites an agent to invoke a command from inside an example.

### Configuration changes

None.

### Verification

- `MEM.md` reports version 1.1.0.
- `MEM HELP` lists the core commands.
- `MEM STATUS` reports version, `KB_ROOT`, configuration in effect, and registered extensions.
- A recognized command with no implementation is reported as such, neither guessed nor ignored.
- With `extensions_enabled: false`, commands are reported as disabled by configuration.
- Prompts without a reserved command behave as they did in 1.0.4.
- Command tokens quoted inside documentation or examples do not activate.
- Existing extension registrations are preserved.

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

