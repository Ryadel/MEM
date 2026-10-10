# Changelog

All notable MEM changes are documented in this file.

MEM uses `MAJOR.MINOR.BUILD` versioning. Version-to-version migration steps are documented in [MEM.upgrade.md](MEM.upgrade.md).

## 1.1.8 - 2026-10-10

### Added

- Added **agent credit**. With `agent_credit: false`, the default, the agent adds no line crediting an AI agent,
  model or tool — no `Co-authored-by:` trailer naming it, no "Generated with" line, no assistant signature — to
  commit and tag messages, pull or merge request descriptions, release notes or code comments, including when its
  own tooling adds one by default. An explicit request for a specific commit is honored; trailers crediting people
  are unaffected; history is never rewritten.
- Whatever `agent_credit` says, the agent commits, tags and pushes **as the user**: the configured git identity and
  the configured credentials, never an `--author`, `user.name` / `user.email` override, `GIT_AUTHOR_*` /
  `GIT_COMMITTER_*` variable or credential naming an agent, unless the user explicitly asks.
- Added the **`mem-workspace`** extension, 1.0.0: the knowledge base in a private repository beside a public one,
  under a workspace folder that is not a repository, with an optional wiki. It provides `MEM WORKSPACE`
  (cross-repository status), `MEM WORKSPACE CHECK` (layout, and no private path or knowledge base file in a public
  repository, including its history) and `MEM WORKSPACE INIT` (records the roles in `custom/workspace.md`, its
  bootstrap entry, after confirmation). Read-only local `git` only, no external actions. While active, the agent
  routes each file to its repository, moves tracked files with `git mv` and commits the move on its own, and lists
  pending commits per repository in push order. Ships a setup and migration guide, including carrying history
  across repositories, and adapters for Visual Studio and VS Code.

### Configuration

- Added `agent_credit: false`.

## 1.1.7 - 2026-10-09

### Added

- Added **retention** for agent temporary files. At the start of a session the agent deletes every top-level
  entry of `agent_tmp_dir` unused for `agent_tmp_retention_days` days. Age is the newest modification time inside
  the entry, so a cache reused every day never expires; entries are deleted whole, never file by file, so an
  isolated build is never left half-deleted.
- Added a **layout** inside the folder: a reused cache keeps a fixed name such as `build/`; everything else goes
  in one folder per task, `YYYY-MM-DD-<slug>/`.
- The end-of-session checklist now checks that nothing the user needs is left only in `agent_tmp_dir`, the
  guarantee retention depends on.

### Changed

- Corrected the reason given for the folder's location: the .NET SDK excludes folders whose name begins with a dot
  from a project's default items, as well as `bin/` and `obj/`. The name of `agent_tmp_dir` should therefore begin
  with a dot.
- Covered three cases the 1.1.6 rule did not: a repository root that is itself a project folder, a workspace of
  several repositories that is not one, and `git check-ignore` run outside any repository (exit code 128), where
  the folder still gets its `.gitignore`, which also marks it as the agent's.
- `README.md`: `/MEM/` is described as a convention, not a requirement for `KB_ROOT`; apostrophes normalized to
  ASCII.

### Configuration

- Added `agent_tmp_retention_days: 7`. `0` disables retention.

## 1.1.6 - 2026-10-08

### Added

- Added **agent temporary files**: everything the agent produces for its own use — alternate build output, test
  runs, scratch scripts, intermediate conversions — goes in one folder at the repository root, and nowhere else.
- The folder is excluded from git **before** it is created. The agent checks with
  `git check-ignore -q <agent_tmp_dir>/probe`; if the folder is not ignored, its first file is a `.gitignore`
  containing `*`, which touches no tracked file. A root `.gitignore` line remains available with confirmation.
- A pre-existing folder with that name is not adopted: one the agent did not create is never emptied, and the
  agent asks before writing into it.
- Added a rule for **isolated builds**: when an IDE holds the regular build's outputs, the agent builds into
  `<agent_tmp_dir>/build/` and redirects intermediates as well as outputs — on .NET 8 and later with
  `dotnet build --artifacts-path`.

### Configuration

- Added `agent_tmp_dir: ".tmp"`.

## 1.1.5 - 2026-10-05

### Added

- Added **libraries and runtimes** to `mem-toolbox`. `python` and `node` are catalogue entries of the new
  `kind: runtime`; a library declares `requires: <runtime>`, its `package` name, and its `import` name where the
  two differ.
- Added **agent environments** to `mem-toolbox`: one per runtime, per host, recorded in the host file as
  `<runtime> env`. Whether it is a dedicated environment under `<tools root>/envs/` or the system interpreter is
  always asked, never preset, and the trade-offs are stated every time.
- Added **approved installs**. The agent may install a package into the dedicated environment after explicit
  approval naming package, version, environment and registry, and only a name taken from a catalogue entry or
  given by the user. Runtimes, CLI tools and system interpreters remain proposal-only. `mem-toolbox` therefore
  now declares `external actions: yes`, and the approval is required even when
  `extensions_allow_external_side_effects` is true.
- Added `min version` to catalogue entries, and the `outdated` status for a tool that works but is below it.
- Added `MEM TOOLS CHECK`, which probes runtimes and agent environments on request and writes only the host file.
  It never installs, never reaches the network, and never runs at session start.
- Added 18 catalogue entries: `python`, `node`, `reportlab`, `pypdf`, `pdfplumber`, `qpdf`, `pandoc`, `typst`,
  `python-docx`, `openpyxl`, `python-pptx`, `pillow`, `svgo`, `exiftool`, `pandas`, `duckdb`, `jq`,
  `matplotlib`, each licence read from upstream on 2026-10-05.

### Changed

- `mem-toolbox` is now 1.0.2. Its catalogue covers media, documents and data, split into per-domain sub-indexes
  — `catalog/index.media.md`, `index.documents.md`, `index.data.md` — under a `catalog/index.md` that now lists
  runtimes and domains.
- "The agent never installs" now has one exception, bounded by isolation: an approved package into the dedicated
  environment, which deleting one folder undoes. Entries still never carry an install command.
- The boundary with `references/` now also covers project dependencies: a library the product depends on belongs
  to the project's own manifest, never to an agent environment.

### Configuration

- No option was added, removed or renamed.

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

