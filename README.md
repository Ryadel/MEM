<p align="center">
  <img src="./img/MEM-logo.svg" alt="MEM logo" width="40%">
</p>

# MEM: Markdown Embedded Memory

**MEM** is a Markdown-based operating memory layer for AI-assisted projects.

It gives AI agents a readable, indexed and persistent project memory that can be stored in the repository, reviewed by humans, updated over time and reused across sessions. Its purpose is simple: prevent useful project context from disappearing inside chat history.

MEM is designed for software projects, technical documentation, infrastructure repositories, security work, editorial workflows and any long-running technical activity where context, decisions and troubleshooting knowledge matter.

Release notes are tracked in [CHANGELOG.md](CHANGELOG.md). Version-to-version migration steps are tracked in [MEM.upgrade.md](MEM.upgrade.md).

## Compatibility

MEM does not require a specific runtime, dedicated SDK or proprietary integration: it is compatible with any AI coding assistant or LLM agent that can read Markdown files, inspect a repository and update project files.

This means it can be used with tools such as **Claude Code**, **OpenAI Codex**, **GitHub Copilot**, **Cursor**, **Windsurf**, **Visual Studio Code** with AI extensions, **Visual Studio** with chat extensions or coding assistants, as well as any custom agent based on models such as GPT, Claude, Gemini, Llama or similar.

The only practical requirement is that the tool can access the `MEM.md` file and treat it as the project’s persistent operating context. From that point on, MEM remains vendor-independent: the agent reads the instructions, consults the knowledge base, updates logs and documentation, and keeps the context aligned with the repository according to the rules defined by the project.

## How to use

Installing and using MEM is incredibly simple: you can choose between automatic (LLM-driven) or manual (user-driven) install.

### Automatic install

The fastest way is to give your AI coding assistant or LLM agent the URL of the latest `MEM.md` file and ask it to install MEM in your project.

A typical prompt can be:

```text
Download the latest MEM.md file from https://raw.githubusercontent.com/Ryadel/MEM/main/src/MEM.md
and place it under /MEM/MEM.md in this repository.

Then read and apply /MEM/MEM.md as the persistent operating memory for this project.
Initialize the MEM knowledge base if required, 
then inspect the project before making implementation claims.
```

The agent should create the target folder if it does not exist, save the file locally, then use it as the bootstrap memory for the project.

### Manual install

1. Get the latest version of the `MEM.md` file from the MEM GitHub repository.
2. Place it under a suitable root-level folder of your project, such as `/MEM/`.
3. Open your favourite AI coding assistant or LLM agent.
4. Ask the agent to read and apply the `MEM.md` file before doing any non-trivial work on the project.
5. Let the agent initialize or update the project knowledge base as work progresses.

A typical first prompt can be:

```text
Read and apply /MEM/MEM.md as the persistent operating memory for this project.
Initialize the MEM knowledge base if required, 
then inspect the project before making implementation claims.
```

From that point on, the agent can use MEM as the project’s persistent context layer: it can read existing documentation, update daily logs, record decisions, preserve troubleshooting notes and keep the knowledge base aligned with the actual source code.

## What is MEM

AI agents can help with coding, analysis, refactoring, documentation and troubleshooting, but they still lose operational context too easily.

A session may produce:

- a useful explanation of how a module works;
- a bug diagnosis and its solution;
- a technical decision;
- a refactoring plan;
- project-specific conventions;
- notes about files, commands, dependencies or constraints.

Without a durable project memory, that knowledge often remains trapped in a conversation and becomes hard to recover later.

MEM solves this by turning Markdown files into a structured project knowledge base that agents can read before doing meaningful work and update after producing durable information.

## Core idea

MEM is built around a bootstrap file named `MEM.md`.

When an AI agent is asked to work on a project, it should read `MEM.md` first. That file defines how the project memory is loaded, where the knowledge base lives, which files should be consulted, when the memory should be updated and which rules apply to the current project.

The source code remains the implementation source of truth. MEM acts as the maintained explanation layer: it documents how the project works, why decisions were made, which conventions apply, what changed and what should be remembered for future sessions.

## Key features

### Persistent project memory

MEM gives each project a durable memory that survives individual chat sessions. The knowledge base can store architecture notes, project documentation, conventions, decisions, tasks, troubleshooting notes, references and daily activity logs.

### Markdown-first design

All project memory is stored in plain Markdown files. This keeps MEM easy to read, easy to version, easy to review in pull requests and easy to edit without a dedicated platform.

### Structured knowledge base

MEM uses a clear folder structure so information has a predictable place. Architecture goes under `architecture/`, decisions under `decisions/`, troubleshooting notes under `troubleshooting/`, daily logs under `logs/`, and so on.

### Activity logs

Daily logs preserve meaningful work performed during a session without storing raw conversation history. A good log captures what changed, which files were touched, what remains pending and which notes may help future sessions.

### Reserved commands

MEM defines a small set of commands the agent recognises when they appear on their own line in a prompt, such as `MEM HELP` or `MEM STATUS`. They make frequent operations deterministic: the agent follows a documented procedure instead of inferring one from prose.

### Remote MEM source

MEM can be loaded from a remote source. In this mode, the local `MEM.md` acts as a bootstrap loader and the active operating context is fetched from a configured remote URL.

This is useful when multiple repositories need to share common agent behavior, documentation rules, safety boundaries or operational conventions.

### Extensions

MEM supports optional task-specific extensions through the `extensions/` folder. Extensions can define routines, checklists, commands, API calls, notification flows or other operational behavior that does not belong in the general project knowledge base.

External actions, such as deploys, HTTP requests, ticket creation or writes to external systems, require explicit confirmation unless the project configuration allows them.

## Default knowledge base structure

A typical MEM knowledge base looks like this:

```text
KB_ROOT/
  MEM.md
  MEM.config.md
  MEM.remote-cache.md
  MEM.index.md
  MEM.project.md
  architecture/
  docs/
  conventions/
  decisions/
  logs/
  drafts/
  tasks/
    index.md
    current/
    done/
  troubleshooting/
    index.md
    current/
    done/
  references/
  glossary/
  changelog/
  archive/
    index.md
  extensions/
    EXT.md
    EXT.index.template.md
    <extension-id>/
      index.md
      <base-content>/
      custom/
        index.md
```

## Main files and folders

### `MEM.md`

The bootstrap memory for the project. It defines the general operating rules for the AI agent and the knowledge base.

### `MEM.config.md`

Optional project-specific configuration. It can override default values such as language, link style, build commands, test commands, remote MEM settings and extension behavior.

### `MEM.index.md`

The navigation entry point of the knowledge base. It should list important pages grouped by category, with short descriptions.

### `MEM.project.md`

A high-level description of the project: name, purpose, domain, stack, runtime environments, dependencies, repository structure, known constraints and notes for future agents.

### `architecture/`

Current architecture documentation. These files should describe how the system works now, not how it should ideally work.

### `docs/`

Broader technical and functional documentation, such as feature overviews, onboarding notes, local setup instructions, release process notes or API documentation.

### `conventions/`

Project-specific rules and patterns: coding style, naming, comments, testing, Git usage, errors, logging, API design, database conventions and security practices.

### `decisions/`

Architecture Decision Records. Use this folder for meaningful technical decisions, especially when they affect architecture, deployment, authentication, data models, dependencies or project-wide conventions.

### `logs/`

Daily activity logs named as `YYYY-MM-DD.md`. These logs should be factual and concise. They should not contain raw chain-of-thought or full conversation transcripts.

### `tasks/`

Backlog items, bugs, refactoring notes, technical debt and active work items. Use `tasks/index.md` as the task index, `tasks/current/` for open items and `tasks/done/` for closed items.

### `troubleshooting/`

Runbooks for diagnosed errors and recurring issues. Use `troubleshooting/index.md` as the troubleshooting index, `troubleshooting/current/` for active or recurring items and `troubleshooting/done/` for closed items. A troubleshooting note should include the symptom, context, known or suspected cause, solution and related files.

### `references/`

External links, useful commands, dependency references, API references and environment variable names. Do not store real secret values.

### `archive/`

Obsolete or superseded knowledge that should be preserved but no longer belongs in the active working path. Ordinary completed tasks and resolved troubleshooting items belong in their area's `done/` folder.

### `extensions/`

Optional Extensions. Each extension lives in its own folder and provides task-specific operating instructions.

## Reserved commands

A reserved command is written on its own line in the prompt:

```text
MEM <COMMAND> [target]
```

The line must start with `MEM`, and both words must be uppercase. Commands apply to the current request only.

These are available without installing anything:

| Command | Purpose |
|---|---|
| `MEM HELP` | List the available commands |
| `MEM STATUS` | Report MEM version, `KB_ROOT`, configuration in effect, registered extensions |
| `MEM INIT` | Run first-time initialization |
| `MEM UPDATE` | Update `MEM.md` from `mem_update_url` and apply upgrade notes |
| `MEM LINT` | Review the knowledge base |
| `MEM FORCE` | Re-anchor the session and report which MEM files were read and written |

`MEM FORCE` is a modifier: it applies to the whole request regardless of where it appears, and can be combined with another command.

A command is recognised only when it is genuinely an instruction. Mentioning one in a sentence, quoting one, or showing one inside a code block does not trigger it — including the examples in this document. When a command does activate, the agent announces it on the first line of its reply, so an incorrect activation is visible and can be corrected immediately.

If a command is recognised but nothing implements it, the agent says so. It will not guess what the command meant, and will not silently ignore the line.

Extensions can add further commands. Setting `extensions_enabled: false` disables everything except the core commands above.

If a command is recognised but nothing local implements it, the agent checks the extension manifest. When a distributed extension provides that command, it offers to install it — once, and never without a confirmation naming the files and the source URL.

### Commands from `mem-commands`

The `mem-commands` extension adds three more. It is not installed by default; the agent offers it the first time you use one of them.

| Command | Purpose |
|---|---|
| `MEM REVIEW <target>` | Assess a plan, task or troubleshooting note **before** it is implemented |
| `MEM CHECK <target>` | Verify work that was **declared complete** against the implementation that actually exists |
| `MEM DEFINE <COMMAND>` | Write a command of your own |

`REVIEW` and `CHECK` are the same machinery pointed at different assumptions, which is why they are one extension: `REVIEW` never treats unbuilt work as a defect, `CHECK` never takes a completion claim at face value. Both are read-only — they report findings with a severity and a verdict, and never change a file, a task status, or the repository.

`CHECK` runs your build and test commands only if you set them explicitly in `MEM.config.md`; auto-detected commands are never executed, and anything it could not run is reported as unverified rather than assumed to pass.

`DEFINE` is the exception that writes: it creates a definition under the extension's `custom/` folder, with confirmation. A project command is worth defining when a procedure has several steps, recurs, needs judgement, and costs something when a step is skipped — a release checklist rather than a one-off.

### Tooling from `mem-toolbox`

The `mem-toolbox` extension answers two questions an agent otherwise re-derives every session: which CLI tool to use for a task, and whether it is actually installed here. It adds `MEM TOOLS`, which lists what is known.

It keeps those two answers apart, and that separation is the point. Which tool a project uses is portable knowledge and belongs in the repository. Whether a tool exists at a given path is true of one machine only, so it lives in per-host files. Recording availability as a plain fact would let an agent on a colleague's machine read "available", skip asking you, and fail — so availability is always stamped with a host and a date, and evidence from another machine is treated as a hint rather than proof.

Per-host observations are written automatically, since they only record what a version command answered. Catalogue entries need confirmation, because deciding "this is what we use for X" is a judgement rather than an observation. Absence is recorded too: a tool you declined is not proposed again next session.

MEM ships a small image-processing catalogue — ImageMagick, vips, oxipng, resvg, realesrgan-ncnn-vulkan — with each licence read from upstream and dated. Your own entries override it, since local knowledge is closer to the truth. The agent never installs anything: entries carry project URLs, never install commands.

## Configuration

Project-specific configuration lives in `MEM.config.md`.

If `MEM.config.md` is missing, MEM uses default values. If `MEM.config.md` exists but omits an option, MEM uses the default value for that option from `MEM.md`. A minimal configuration may look like this:

```yaml
kb_root: "."
kb_language: "en"
user_language: "auto"
link_style: "markdown"

mem_source: "local"
mem_remote_url: null
mem_remote_cache: false
mem_remote_cache_path: "MEM.remote-cache.md"
mem_remote_fail_policy: "stop"
mem_update_url: "https://raw.githubusercontent.com/Ryadel/MEM/main/src/MEM.md"
mem_upgrade_url: "https://raw.githubusercontent.com/Ryadel/MEM/main/MEM.upgrade.md"
mem_manifest_url: "https://raw.githubusercontent.com/Ryadel/MEM/main/src/extensions/manifest.md"
mem_auto_update: true

primary_stack: "auto-detect"
package_manager: "auto-detect"
build_command: "auto-detect"
test_command: "auto-detect"
run_command: "auto-detect"
default_branch: "auto-detect"

update_daily_log: true
create_adr_for_decisions: true
document_troubleshooting: true
document_minor_changes: false
auto_create_missing_kb_files: true
auto_update_kb_after_code_changes: true
move_completed_tasks_to_done: true
move_completed_troubleshooting_to_done: true

extensions_enabled: true
extensions_allow_external_side_effects: false
extensions_require_confirmation: true

ask_before_large_reorganization: true
prefer_small_incremental_updates: true
require_source_references: true
mark_uncertainty: true
```

## Precedence rules

MEM follows this precedence order:

1. explicit user instruction for the current task;
2. explicit values in `MEM.config.md`;
3. defaults defined in `MEM.md`;
4. auto-detected values from reliable project files.

An agent must not overwrite explicit values in `MEM.config.md` without user confirmation.

## Remote MEM source

By default, MEM is loaded from the local `MEM.md`.

A project can configure a remote MEM source:

```yaml
mem_source: "remote"
mem_remote_url: "https://example.com/path/to/MEM.md"
mem_remote_cache: true
mem_remote_cache_path: "MEM.remote-cache.md"
mem_remote_fail_policy: "fallback_cache"
```

When `mem_source` is set to `remote` and `mem_remote_url` is not empty, the local `MEM.md` acts as a bootstrap loader. The agent must fetch the remote MEM document and use it as the active operating context.

Supported remote failure policies:

```yaml
mem_remote_fail_policy: "stop"
```

Stops the work and reports that the remote MEM could not be loaded.

```yaml
mem_remote_fail_policy: "fallback_local"
```

Continues with the local `MEM.md` and reports the fallback.

```yaml
mem_remote_fail_policy: "fallback_cache"
```

Continues with the cached remote MEM file if available; otherwise stops.

`MEM.remote-cache.md` is a technical cache file. It should not be linked from `MEM.index.md` and should not be treated as navigable project documentation.

Remote MEM content must not override explicit user instructions or higher-priority system and developer instructions. Remote MEM files must not contain secrets.

## Updating MEM

When an agent is asked to `update MEM`, it updates the local `MEM.md` from `mem_update_url`.

After a successful update, the agent should fetch the current [MEM.upgrade.md](https://raw.githubusercontent.com/Ryadel/MEM/main/MEM.upgrade.md) from `mem_upgrade_url`. `MEM.upgrade.md` is the LLM-friendly, operational counterpart to the human-readable [CHANGELOG.md](CHANGELOG.md): it lists the patches and structural changes an agent may need to apply. Upgrade steps should be applied sequentially from the previous MEM version to the new MEM version: BUILD upgrades first, then MINOR upgrades, then MAJOR upgrades.

If `mem_auto_update: true`, the agent attempts the same update when creating a new daily log file (`logs/YYYY-MM-DD.md`). The daily log starts with a short MEM auto-update status line, using one of these statuses:

- `succeeded` — the local `MEM.md` was updated;
- `up-to-date` — the update was attempted, but no change was needed;
- `failed` — the update was attempted but could not be completed.

## Extensions

Extensions are optional MEM modules for task-specific behavior.

They may define:

- repeatable routines;
- checklists;
- commands;
- API calls;
- notification flows;
- release or deployment steps;
- incident handling procedures;
- integration-specific workflows.

The extension entry point is:

```text
extensions/EXT.md
```

Each extension must live in its own folder:

```text
extensions/<extension-id>/index.md
```

Every extension is split into two layers:

- a **base** layer — how the extension works, plus any content MEM ships with it. It is maintained upstream and replaced when the extension is updated, so local edits to it are lost;
- a **custom** layer under `custom/`, governed by `custom/index.md`. It is never shipped and never touched by an update, and it is where project-specific entries belong.

The base layer points to `custom/index.md`, so the customisation surface is always in the same place. An extension with nothing to customise says so. An extension you have not customised simply has no `custom/` folder, which is a normal state.

Each extension declares whether base or custom wins when both define the same entry, because the right answer differs by extension: shadowing a command is a hijack risk, while overriding a reference entry with local knowledge is usually correct.

### The manifest, and what authorises an extension

MEM publishes a manifest listing the extensions it distributes, what each one provides, and the exact files that make it up. That file list is also the update set: an update writes only what the manifest names, which is why your `custom/` folders and your `EXT.md` are safe by construction rather than by a rule someone has to remember.

The manifest is a catalogue, not a permission slip. It is fetched over the network and its URL can be overridden in configuration, so it never decides what runs in your repository. An extension is used because its files are in your repository and it is registered `active` in `EXT.md` — both reviewable in a pull request like anything else.

That splits cleanly into two behaviours:

- **installing** an extension, or letting one write files, run commands or reach outside the repository, needs your explicit approval — a notice afterwards would be worthless, the change has already happened;
- **using** an extension you already registered needs disclosure, not another prompt. The agent names it on the acknowledgement line, and says when an extension is one you wrote rather than one MEM distributes.

An extension outside the manifest is perfectly legitimate — writing your own is the point of the custom layer. It simply gets no automatic offer to install and no borrowed trust.

An agent should read Extensions when:

- the user explicitly asks for extension behavior;
- the current task clearly matches an active extension listed in `extensions/EXT.md`;
- a relevant knowledge base page points to an extension.

Extensions must not override user instructions, `MEM.md` or `MEM.config.md`. They may only refine behavior for their own task domain.

## External actions

Extensions may describe actions that change state outside the local repository, such as:

- HTTP requests;
- notifications;
- deploys;
- ticket creation;
- writes to external systems.

These external actions require explicit user confirmation unless this is explicitly allowed in `MEM.config.md`:

```yaml
extensions_allow_external_side_effects: true
```

Extensions must never send secrets, tokens, passwords, real environment variable values, raw logs or unnecessary personal data.

## Recommended agent workflow

A MEM-aware agent should follow this workflow:

1. read `MEM.md`;
2. read `MEM.config.md`, if present;
3. read `MEM.index.md`, if present;
4. read `MEM.project.md`, if present;
5. read `extensions/EXT.md`, if present and extensions are enabled;
6. read relevant files under `architecture/`, `docs/`, `conventions/`, `decisions/`, `tasks/`, `troubleshooting/` or `extensions/`;
7. inspect source code before making implementation claims;
8. perform the requested work;
9. update the knowledge base when meaningful, durable knowledge was discovered or produced.

## When to update the knowledge base

Update MEM when discovering durable information, such as:

- how a module works;
- why a bug occurred and how it was fixed;
- project-specific naming or coding conventions;
- recurring errors and tested solutions;
- technical decisions;
- new dependencies;
- database behavior;
- security constraints;
- local setup or deployment requirements.

Preserve useful conclusions, not entire conversations.

## What not to store

Do not store:

- raw chain-of-thought;
- temporary speculation with no future value;
- failed intermediate attempts with no diagnostic value;
- trivial typo fixes;
- large source-code dumps;
- secret values such as passwords, tokens or credentials.

Environment variable names may be documented, but real values must never be written to the knowledge base.

## ADRs

Create or update an Architecture Decision Record when a meaningful decision is made, such as:

- choosing a new library, framework or external service;
- changing architecture, authentication, deployment or database design;
- establishing a project-wide convention;
- accepting a significant tradeoff;
- deprecating an existing pattern;
- introducing a security-relevant design.

Recommended ADR filename:

```text
decisions/YYYY-MM-DD-short-decision-title.md
```

Recommended sections:

```text
Context
Decision
Rationale
Alternatives Considered
Consequences
Follow-up
```

When a decision replaces an older one, mark the old ADR as superseded and link to the new decision. Do not delete superseded decisions.

## Knowledge base quality

MEM documentation should be:

- concise;
- practical;
- factual;
- easy to scan;
- linked to source files when useful;
- explicit about uncertainty.

Avoid generic documentation that is not tied to the project. Avoid obsolete claims left unmarked. Avoid duplicating large chunks of source code.

When documenting behavior inferred from code, include file paths and relevant symbols. If something has not been verified, mark it clearly.

Useful markers include:

```text
Unverified
Needs confirmation
Inferred from code
Confirmed by runtime test
Deprecated
```

## First-time initialization

When initializing MEM in a new repository, start with a lightweight structure:

```text
MEM.index.md
MEM.project.md
architecture/system-overview.md
conventions/coding-style.md
conventions/naming.md
conventions/comments.md
tasks/index.md
tasks/current/backlog.md
logs/YYYY-MM-DD.md
```

Use placeholders where information is not known yet:

```markdown
> TODO: Fill this section after inspecting the codebase.
```

Do not invent project details.

## Example daily log

```markdown
# 2026-04-30

## Work completed

- Reviewed authentication flow and confirmed token validation path.
- Updated `architecture/authentication.md` with the current request flow.
- Added troubleshooting note for invalid issuer errors.

## Files inspected

- `src/Web/Program.cs`
- `src/Web/Controllers/AuthController.cs`
- `src/Application/Auth/TokenService.cs`

## Pending

- Add integration test for expired token handling.
- Confirm production issuer configuration.
```

## Example troubleshooting note

```markdown
# Invalid JWT issuer

## Symptom

API requests fail with `SecurityTokenInvalidIssuerException`.

## Context

Observed during local authentication testing.

## Cause

The configured issuer in `appsettings.Development.json` did not match the issuer used by the token generator.

## Solution

Updated the local issuer configuration and restarted the API.

## Related files

- `src/Web/appsettings.Development.json`
- `src/Application/Auth/TokenService.cs`

## Status

Resolved
```

## License

MEM is released under the [MIT License](LICENSE).

See [CHANGELOG.md](CHANGELOG.md) for release notes and [MEM.upgrade.md](MEM.upgrade.md) for version-to-version upgrade steps.
