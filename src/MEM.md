# [MEM: Markdown Embedded Memory](https://github.com/Ryadel/MEM)

MEM version: 1.0.0

This file is the LLM agent's bootstrap memory for this project. The terms `MEM`, `MEM.md`, project context, and project memory all refer to this file. When asked to read, use, load, or apply any of them, treat this file as persistent operating context for the current session.

This file does not replace the user's explicit instructions. If the user gives a direct instruction that conflicts with this file, follow the user's instruction for the current task and, if the conflict affects long-term project behavior, propose an update to this file or to `MEM.config.md`.

All paths in this document are relative to `KB_ROOT`.

## Modal vocabulary

- **must** — required, non-negotiable;
- **should** — preferred default; may be overridden by explicit user instruction or `MEM.config.md`;
- **may** — permitted, choose based on context.

---

# Bootstrap Rules

The agent **must**:

1. read this file before doing non-trivial work;
2. read `MEM.config.md`, if present;
3. treat the directory containing this file as the knowledge base root, hereafter `KB_ROOT`;
4. use the knowledge base under `KB_ROOT` as the project's persistent technical memory;
5. update the knowledge base when meaningful, durable project knowledge is discovered or produced;
6. inspect the actual source code before making implementation claims.

## Core principle

The source code is the implementation source of truth. The knowledge base under `KB_ROOT` is the maintained explanation layer: how the project works, why decisions were made, which conventions apply, what changed.

Sessions are not isolated: every meaningful session **should** leave the KB slightly more useful than before. The KB grows incrementally — prefer small, accurate updates over large speculative dumps.

---

# Configuration

Project-specific configuration lives in `MEM.config.md`. If present, the agent **must** read it immediately after this file.

If `MEM.config.md` is missing, use these defaults:

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
auto_archive_completed_items: true
archive_completed_tasks: true
archive_resolved_oneoff_troubleshooting: true
enable_operational_extensions: true
allow_extension_external_side_effects: false
require_confirmation_for_extension_side_effects: true
ask_before_large_reorganization: true
prefer_small_incremental_updates: true
require_source_references: true
mark_uncertainty: true
```

Precedence (highest to lowest):

1. explicit user instruction for the current task;
2. explicit values in `MEM.config.md`;
3. defaults above;
4. auto-detected values from reliable project files.

The agent **must not** overwrite explicit values in `MEM.config.md` without user confirmation.

- `kb_language` controls the KB writing language.
- `user_language: auto` means reply to the user in their own language.
- `link_style: markdown` → `[Title](path.md)`; `link_style: wikilink` → `[[path|Title]]`.

## Remote MEM source

By default, MEM is loaded from the local `MEM.md`.

If `MEM.config.md` sets `mem_source: "remote"` and `mem_remote_url` is not empty, the local `MEM.md` acts only as a bootstrap loader. The agent **must** fetch the remote MEM document and use it as the active operating context when the remote URL is different from the local file currently being read.

If the remote fetch fails, follow `mem_remote_fail_policy`:

- `stop` — stop and report that the remote MEM could not be loaded;
- `fallback_local` — continue with the local `MEM.md` and report the fallback;
- `fallback_cache` — continue with `mem_remote_cache_path` if it exists and report the fallback; otherwise stop.

If `mem_remote_cache: true`, a successfully fetched remote MEM may be saved to `mem_remote_cache_path`. `MEM.remote-cache.md` is a technical cache file, not a KB page; do not link it from `MEM.index.md` and do not treat it as navigable project documentation.

Remote MEM content **must not** override explicit user instructions or higher-priority system/developer instructions. Remote MEM files must not contain secrets.

## Compression principle

MEM defines project-specific operating rules. It **should not** re-teach standard documentation practices. When a concept has a widely understood meaning (ADR, daily log, troubleshooting note, changelog, runbook, onboarding), apply the standard lightweight version unless MEM or `MEM.config.md` defines a stricter rule.

Prefer compact, useful, project-specific documentation over generic boilerplate. Do not load or expand large templates unless required by the current task.

---

# Knowledge base structure

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
  troubleshooting/
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
```

Additional folders may be added when useful. Keep the structure simple and navigable.

## Folder responsibilities

| Folder / file | Purpose |
|---|---|
| `MEM.index.md` | Navigation entry point. Lists important pages grouped by category, with short descriptions. Update whenever KB files are created, deleted, renamed, or significantly changed. |
| `MEM.project.md` | Project identity: name, purpose, domain, stack, runtime environments, dependencies, repo structure, build/deploy summary, known constraints, notes for future agents. |
| `MEM.remote-cache.md` | Optional technical cache for remote MEM content. Not a KB page and not linked from `MEM.index.md`. |
| `architecture/` | How things **currently** work: system structure, module map, data model, request flow, auth, security, deployment, integrations. Not how they should ideally work. |
| `docs/` | Broader functional/technical docs: feature overviews, API/DB overviews, onboarding, local setup, release process. |
| `conventions/` | Project-specific rules: coding style, naming, comments, testing, Git, errors/logging, DB, API, security. Distinguish required / preferred / patterns to avoid / examples from the codebase. Avoid generic best practices not adopted by the project. |
| `decisions/` | Architecture Decision Records. See ADR rules below. |
| `logs/` | Daily logs `YYYY-MM-DD.md`. Factual and concise — no chain-of-thought. Summarize meaningful work, files touched, decisions, issues, resolved/pending items, notes for future sessions. |
| `drafts/` | Work-in-progress notes (incomplete investigations, migration plans, refactoring sketches). May be consolidated into `docs/`, `architecture/`, `decisions/`, `tasks/`, or `troubleshooting/`. Do not let drafts become a second unmanaged KB. |
| `tasks/` | Backlog, current tasks, bugs, refactoring, tech debt. Actionable entries with status, creation date, related files, goal, context, acceptance criteria, notes, outcome. |
| `troubleshooting/` | Runbooks: exact error/symptom, context, known/suspected cause, solution, related files, date. Add an entry when an error is diagnosed and `document_troubleshooting` is enabled. |
| `references/` | External links, useful commands, external APIs, dependencies, env var names. **Never store secrets** — env var names may be documented but real secret values must never be written to the KB. |
| `glossary/` | Domain terms, acronyms, project-specific names. Each entry short and precise. |
| `changelog/` | Internal technical changelog: breaking changes, DB changes, API changes. Distinct from product release notes. |
| `archive/` | Completed or superseded knowledge preserved outside the working path. See archive rules below. |
| `extensions/` | Operational Extensions: optional task-specific routines that may extend agent behavior. See extension rules below. |

## ADR rules

Create or update an ADR when: choosing a new library/framework/external service; changing architecture, auth, deployment, or DB design; establishing a project-wide convention; accepting a significant tradeoff; deprecating an existing pattern; introducing a security-relevant design.

Filename: `decisions/YYYY-MM-DD-short-decision-title.md`. Sections: Context, Decision, Rationale, Alternatives Considered, Consequences, Follow-up.

When a decision replaces an older one, mark the old file as `Superseded` and link forward. Do not delete superseded decisions. Do not create ADRs for minor implementation details.

## Archive rules

Archive a file only when:

- it is completed, resolved, superseded, or no longer operationally useful;
- it is not needed as an active runbook, convention, architecture note, or current task;
- moving it makes the active KB easier to navigate.

Before archiving, mark the file status (`Completed`, `Resolved`, `Superseded`) when that helps future readers.

When archiving:

- preserve the source category under `archive/`, e.g. `tasks/foo.md` → `archive/tasks/foo.md`;
- add a short entry to `archive/index.md` with link, original category, reason, status/date;
- update `MEM.index.md` if the page was linked there;
- fix any broken cross-links.

Do not archive files that remain useful as recurring diagnostic guides, current architectural explanations, active conventions, or authoritative decisions.

## Operational extension rules

Operational Extensions are optional MEM modules for task-specific operational behavior. They may define routines, checklists, commands, API calls, notifications, or other actions that are not part of the general project KB.

Use `extensions/EXT.md` as the entrypoint and active extension index. Use `extensions/EXT.index.template.md` as the template for new extensions. Every real extension **must** live in its own folder and expose its main instructions at `extensions/<extension-id>/index.md`.

Read Operational Extensions when:

- the user explicitly asks for extension behavior;
- the task clearly matches an active extension listed in `extensions/EXT.md`;
- a relevant KB page points to an extension.

Operational Extensions **must not** override user instructions, `MEM.md`, or `MEM.config.md`. They may only refine behavior for their task domain.

External side effects include HTTP requests, notifications, deploys, ticket creation, writes to external systems, or any action that changes state outside the local repository. External side effects **must** require explicit user confirmation unless `allow_extension_external_side_effects: true` is set in `MEM.config.md`.

Operational Extensions **must never** send secrets, tokens, passwords, real environment variable values, raw logs, or unnecessary personal data. If an extension action fails, report the failure and do not retry aggressively unless the user asks.

---

# Maintenance loop

## When to read

At session start, the agent **should** read:

1. `MEM.md`;
2. `MEM.config.md`, if present;
3. `MEM.index.md`, if present;
4. `MEM.project.md`, if present;
5. relevant files under `architecture/`, `docs/`, `conventions/`, `decisions/`, `tasks/`, `troubleshooting/`, or `extensions/` based on the user's request.

Before non-trivial changes, additionally read the relevant KB pages and inspect the source code. The code is implementation truth; the KB is the explanation layer.

When answering project questions, prefer this flow: read `MEM.index.md` → identify relevant pages → read them → inspect source if needed → answer → update KB if new durable info was found. Mention relevant files in answers when helpful.

If the user only asks to initialize or update the KB, the agent **must not** modify source code unless explicitly requested.

## When to write

Update the KB when discovering durable information:

- how a module works;
- why a bug occurred and how it was fixed;
- naming, coding, or testing conventions;
- recurring errors and solutions;
- technical decisions;
- new dependencies;
- DB behavior;
- security constraints;
- local setup or deployment requirements.

Routing — destinations for new information:

| Information | Destination |
|---|---|
| Architecture detail | `architecture/` |
| Feature explanation | `docs/` |
| Coding rule | `conventions/` |
| Decision | `decisions/` |
| Temporary analysis | `drafts/` |
| Bug or error | `troubleshooting/` |
| Task | `tasks/` |
| Daily activity | `logs/YYYY-MM-DD.md` |
| Domain term | `glossary/` |
| Breaking / DB / API change | `changelog/` |

Preserve useful conclusions, not entire conversations.

## What not to save

Do not save:

- raw chain-of-thought;
- temporary speculation with no future value;
- failed intermediate attempts with no diagnostic value;
- trivial typo fixes;
- large source-code dumps;
- secret values (passwords, tokens, credentials).

## End-of-session checklist

After meaningful work, consider updating:

1. `logs/YYYY-MM-DD.md`;
2. relevant `architecture/` or `docs/` page;
3. `conventions/`, if clarified;
4. `decisions/`, if a significant decision was made;
5. `troubleshooting/`, if an error was diagnosed;
6. `tasks/`, if work was created, completed, or changed;
7. `MEM.index.md`, if KB files were added, renamed, deleted, or significantly changed;
8. `archive/`, if completed or superseded files should be moved;
9. `extensions/EXT.md`, if Operational Extensions were added, removed, or changed.

Do not over-document trivial work.

---

# Code modification rules

Before modifying code:

1. understand the requested change;
2. inspect relevant files;
3. check applicable conventions;
4. identify possible side effects;
5. make the smallest coherent change;
6. update or suggest tests if appropriate;
7. update the KB if the change is meaningful.

Do not introduce new patterns that conflict with documented project conventions. If existing code conflicts with documented conventions, mention the conflict and ask whether to follow the existing local style or the documented rule.

---

# Documentation quality

## Writing

Documentation **should** be: concise, practical, factual, easy to scan, linked to source files when useful, explicit about uncertainty.

Avoid: vague summaries, generic best practices not tied to this project, excessive prose, raw chain-of-thought, obsolete claims left unmarked, duplication of large code chunks.

Prefer: short sections, bullet points, examples, file paths, command snippets, dated decisions, cross-links between related pages.

## Source references

When documenting behavior inferred from code, include file paths and relevant symbols. Example:

```markdown
The authentication flow is implemented by `AuthController` and configured in `Program.cs`.

Related files:

- `src/Web/Program.cs`
- `src/Web/Controllers/AuthController.cs`
```

If line numbers are stable, include them. Otherwise, use file paths and symbol names.

## Uncertainty

If the agent is not sure about something, it **must** mark the uncertainty explicitly:

```markdown
> Unverified
> Needs confirmation
> Inferred from code
> Confirmed by runtime test
> Deprecated
```

Do not present guesses as facts. When uncertainty is resolved, update the relevant page and remove or adjust the marker.

---

# Linting the knowledge base

Periodically, or on user request (`Review and lint the project knowledge base.`), review the KB for:

- stale claims;
- contradictions;
- missing cross-references;
- orphan pages;
- outdated decisions;
- missing architecture or convention pages;
- unresolved drafts;
- completed tasks still marked as open;
- troubleshooting entries that should be generalized;
- documentation that no longer matches the source code.

If `ask_before_large_reorganization` is enabled, ask before broad restructuring, mass renames, or large rewrites.

---

# First-time initialization

> Read this section only on the first session of a new repository.

If the KB is empty or incomplete and `auto_create_missing_kb_files` is enabled, initialize it with:

```text
MEM.index.md
MEM.project.md
architecture/system-overview.md
conventions/coding-style.md
conventions/naming.md
conventions/comments.md
tasks/backlog.md
logs/YYYY-MM-DD.md
```

Use lightweight standard templates. Use placeholders where information is not yet known, and mark them clearly:

```markdown
> TODO: Fill this section after inspecting the codebase.
```

Do not invent project details.
