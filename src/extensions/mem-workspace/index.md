# Extension: `mem-workspace`

- **version**: 1.0.0
- **provides**: `WORKSPACE`, and routing of files and commits across the repositories of a workspace
- **subcommands**: `CHECK`, `INIT` — closed set
- **bootstrap entry**: `custom/workspace.md` — see "The workspace file"
- **precedence**: **base wins** — the custom layer adds patterns and scoped exceptions; it cannot switch an
  invariant off
- **external actions**: no
- **executable content**: no
- **default mode**: read-only

Keeps the knowledge base out of a public repository by keeping it in a **private sibling repository**, and makes
the agent work correctly across the two.

> "Workspace" here means a folder holding several repositories side by side. It is not an npm, pnpm or Cargo
> workspace, which is one repository holding several packages.

## When this applies

A project with **public** content and **private** development material — this knowledge base, dev notes, draft
plans — that must never reach the public remote. If the whole project is private, keep `KB_ROOT` in the
repository and do not install this extension.

## The layout

```text
<workspace root>/        a plain folder, NOT a repository
  public/                <owner>/<project>          public    the product
  private/               <owner>/<project>.Dev      private   contains KB_ROOT
  wiki/                  <owner>/<project>.wiki     public    optional
```

Folder names are the defaults and **may** differ; `custom/workspace.md` records the real ones. Names that state
the visibility are preferred, because visibility is the axis on which the only irreversible mistake lives.

## Invariants

1. **One repository, one top-level folder.** None is nested inside another, and the workspace root is not a
   repository.
2. **Dependency runs one way.** `private/` **may** reference the others. A public repository **must never**
   reference `private/` — no path, no link, no project or build reference, no CI step.
3. **Each public repository is usable alone.** A clone of it is complete, with nothing missing.
4. **Privacy comes from the remote, not from an ignore line.** `KB_ROOT` is tracked in the private repository.
   A `.gitignore` entry in a public repository is at most a second layer.
5. **Commits are not atomic across repositories.** One piece of work may land as several commits on several
   remotes; nothing enforces that all of them are made.

## The workspace file

`custom/workspace.md` describes this instance, from `WORKSPACE.template.md`: the role table, push order, extra
forbidden patterns, and scoped exceptions. It is the **bootstrap entry**: it is written at installation by the
same procedure as `MEM WORKSPACE INIT`, because every rule below needs to know which folder is which before the
first file is written — exactly when, created lazily, it would not exist.

It holds **relative** paths only, so it is true on every host. The workspace root is derived, never stored: it is
the parent of the private repository's top level (`git -C <KB_ROOT> rev-parse --show-toplevel`).

Roles: exactly one `private` (the one containing `KB_ROOT`), at least one `public`, at most one `wiki`.

## Custom layer

`custom/workspace.md` is the customization surface. `custom/index.md` is created only if the project adds further
files under `custom/`; until then its absence is normal.

Base wins. The custom layer **may** add forbidden patterns and **may** declare an exception — a path, the check it
exempts, and a reason. It **must not** disable a check. Every exception in effect is listed in each `CHECK`
report, so a loosened rule is never silent.

## Behavior

These apply whenever this extension is active, without a command.

### Where a file goes

| Material | Repository |
|---|---|
| The product, its README, changelog, licence, upgrade notes | `public` |
| Contributor- and operator-facing documentation | `wiki`, or `public` when there is no wiki |
| `KB_ROOT`, dev notes, draft plans, review notes, scratch planning | `private` |
| The all-inclusive dev solution or editor workspace | `private` — see `adapters/` |
| Secrets | none of them |

Material written to help the user or the agent work goes to `private`. When in doubt, `private`: two of the three
repositories are public by default.

- Before writing a file, the agent **must** know which repository it is writing into. "The repository root" is
  ambiguous in a workspace: name the folder.
- The agent **must not** write into a public repository any path, link or name that resolves to the private one.
  When a public document needs the information, restate it there; do not point to it.
- Agent temporary files go at the **workspace root** — see `MEM.md`, "Agent temporary files".

### Moving files

Git records no moves: `git log --follow` reconstructs a rename from content similarity. History survives a move
only when the move is made so that git can recognise it.

- **Within one repository**, the agent **must** move a tracked file with `git mv`, never with a plain file-system
  move followed by a separate add and delete, and **should** commit the move on its own, before any edit to the
  moved content. A move and a rewrite in the same commit can fall below the similarity threshold, and the file then
  reads as deleted and re-created.
- **Across repositories** `git mv` cannot work, and a copy starts with no history. When the history matters — moving
  a knowledge base out of a public repository is the usual case — carry it over as described in `setup.md`,
  "Carrying history across repositories". Otherwise copy, and record the source repository and commit in the first
  commit message on the receiving side.
- A move is a change to every inbound link. Search for references to the old path in every repository of the
  workspace, not only the one being edited.

### Before calling a change done

The agent **should** run the status procedure of `MEM WORKSPACE` and list, per repository, what is left to commit
or push, in push order. The half most often forgotten is the daily log in `private`, because it is written last.

### Commits and pushes

The agent **must not** commit or push unless asked. When asked, it proposes one commit per repository and pushes
in the recorded push order — by default `public`, then `wiki`, then `private`: the knowledge base describes the
product, so publishing it first would reference commits that do not exist yet.

Every commit and push is made as the user, in every repository of the workspace — see `MEM.md`, "Agent credit".
A commit message in a public repository **must not** name the private one: invariant 2 covers messages too.

### Where to start the agent

From the workspace root or from `private/`. An agent started inside a public repository alone cannot see
`KB_ROOT`. A pointer file at the workspace root (`AGENTS.md`, `CLAUDE.md`, or whatever the assistant reads) is
never published, because the root is in no repository; it is also not versioned. See `setup.md`, "Pointing the
agent at the knowledge base".

## Commands it runs

The only process this extension starts is `git`, read-only, local: `rev-parse`, `status`, `remote get-url`,
`ls-files`, `grep`, `log`, `check-ignore`. No `fetch`, no network, no write. That closed list is part of what
registering the extension approves; running one of them is disclosed on the acknowledgement line.

## `MEM WORKSPACE`

- **mode**: read-only
- **target**: none

For each role in `custom/workspace.md`, run `git -C <folder> status --porcelain=v1 --branch` and report:

| Role | Folder | Branch | Upstream | Ahead / behind | Changed |
|---|---|---|---|---|---|

Ahead and behind are **as of the last fetch**, and the report says so. A folder that is missing or not a
repository is reported as such, not skipped. End with the commits and pushes left, in push order.

## `MEM WORKSPACE CHECK`

- **mode**: read-only
- **target**: none

Verifies the invariants and reports each finding as `error`, `warning` or `info`. Procedure:
[check.md](check.md).

Run it before pushing a public repository, and after any setup or migration.

## `MEM WORKSPACE INIT`

- **mode**: may-write — `custom/workspace.md` only, with confirmation
- **target**: none

Not the core `MEM INIT`, which initializes the knowledge base; this one describes the workspace around it.

1. Locate the private repository: `git -C <KB_ROOT> rev-parse --show-toplevel`. If that fails, `KB_ROOT` is in
   no repository — report it and stop: there is nothing to describe yet; see `setup.md`.
2. Derive the workspace root as its parent. If the workspace root is itself a repository, report the nesting and
   stop.
3. List the sibling folders that are repository top levels, with `remote get-url origin` and the current branch.
4. Propose a role for each. Visibility **cannot** be verified offline: propose it from the folder name and the
   remote, mark it `recorded, not verified`, and ask.
5. Show the proposed `custom/workspace.md`. Write it only after confirmation. An existing file is shown as a diff
   and is never overwritten unasked.
6. Compare the result against `setup.md` and **list** the steps still missing. Perform none of them.

Run it again whenever a repository is added, renamed, or moved.

## Setup and IDE

- [setup.md](setup.md) — a new workspace, a knowledge base moved out of a public repository, and the agent pointer.
- [adapters/visual-studio.md](adapters/visual-studio.md) — one dev solution that sees and commits every repository.
- [adapters/vscode.md](adapters/vscode.md) — the same with a multi-root workspace file.
