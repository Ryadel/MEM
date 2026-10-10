# Setting up a workspace

Three starting points. In every one of them the agent **proposes** each step and performs none that creates a
repository, changes a remote, or reaches the network: this extension declares no external actions. The user runs
those steps, or approves them one at a time outside this extension.

Finish every scenario with `MEM WORKSPACE INIT`, then `MEM WORKSPACE CHECK`.

## A. A new project

1. Create the workspace root. Do **not** run `git init` in it.
2. Create the repositories on the hosting service: `<project>` public, `<project>.Dev` private. For a GitHub wiki,
   create its first page from the web UI once: an uninitialised wiki has no repository to clone.
3. Clone each into its folder, naming the folder explicitly:
   `git clone <url> public`, `git clone <url> private`, `git clone <url> wiki`.
4. In `private/`, add a `.gitignore` for build output and IDE state **before** the first commit.
5. Install MEM in `private/`: `KB_ROOT` anywhere inside it, for example `private/<project>.Dev/MEM/`.
6. In each public repository's `.gitignore`, add the private folder name and the dev solution or workspace file
   name, as a safety net. Do **not** add the wiki folder.
7. Optional: an IDE adapter — see `adapters/`.
8. Optional: the agent pointer — see below.

## B. A knowledge base tracked in a public repository

The common case: `/MEM/` committed alongside the code.

1. **Stop publishing it first.** Until step 6 is pushed, every push publishes the latest knowledge base.
2. Create the private repository, and turn the folder holding the existing clone into the workspace: move the
   clone to `<root>/public/`, then clone the private repository to `<root>/private/`. Close the IDE first: it
   holds the folder.
3. Bring the knowledge base into `private/`, **with its history** when it matters — see "Carrying history across
   repositories" below. Otherwise copy it, and record the source repository and commit in the first commit message.
4. Verify the copy in `private/` is complete and committed before removing anything from `public/`.
5. In `public/`: `git rm -r <kb-folder>` and add the safety-net `.gitignore` entries from scenario A, step 6.
6. Commit that removal on its own, with a message saying where the knowledge base went **without naming the
   private repository** — invariant 2 applies to commit messages too. Push.
7. Update every pointer to the old path: assistant instruction files, session prompts, the agent pointer.

**What this does not do.** The knowledge base is still in the public repository's history, and in every clone and
fork made before step 6. `CHECK` reports it as check 9. Rewriting public history is destructive, breaks every
existing clone, and removes nothing from copies already taken; deciding to do it is the user's alone. If the
knowledge base ever held a secret, treat the secret as disclosed and rotate it — that is the only fix that works.

## C. A knowledge base ignored inside a public repository

`/dev/MEM/` or similar, listed in `.gitignore` and therefore in **no** repository: no history, no backup.

Follow B, steps 2–7, with a plain copy in step 3 — there is no history to carry. Before step 5, confirm with
`git -C public log --all -- <kb-folder>` that it was never committed. If it was, B's warning applies.

## Moving files

Inside one repository, move tracked files with `git mv` and commit the move on its own, before editing the moved
content — see `index.md`, "Moving files". The rest of this section is about the case `git mv` cannot handle.

### Carrying history across repositories

History cannot be moved; it can be **rewritten into a new branch** of commits and merged into the receiving
repository. Neither technique below changes the public repository's history — removing the files there is still
step 5.

`<kb-folder>` is the knowledge base's path in the public repository, `<destination>` its path inside the private
one, and `<scratch>` a folder under the agent's temporary folder, deleted when done.

**Preferred — `git filter-repo`** (a separate tool, maintained outside git). It rewrites the paths themselves, so
the files keep a continuous, path-based history at their new location. It **must** run on a fresh clone, never on
the working one:

```text
git clone <public-url> <scratch>/kb-export
git -C <scratch>/kb-export filter-repo --path <kb-folder>/ --path-rename <kb-folder>/:<destination>/
git -C private fetch <scratch>/kb-export <branch>
git -C private merge --allow-unrelated-histories FETCH_HEAD
```

Verify: `git -C private log --follow -- <destination>/MEM.index.md` reaches back before the move.

**Fallback — `git subtree`**, git alone. It keeps every commit, but under their **old** paths, joined by a merge
commit that places them under `<destination>/`. A path-based `git log` therefore stops at that merge; the earlier
history is reached through the merge's second parent. Use it when `filter-repo` is not available:

```text
git -C public subtree split --prefix=<kb-folder> -b kb-export
git -C private fetch ../public kb-export
git -C private subtree add --prefix=<destination> FETCH_HEAD
git -C public branch -D kb-export
```

`subtree split` only adds a local branch to `public/`, deleted at the end; it is never pushed.

## Pointing the agent at the knowledge base

An agent started in a public repository cannot see `KB_ROOT`, and the public repository **must not** say where it
is. Two places can hold the pointer:

| Where | Published | Versioned |
|---|---|---|
| A file at the workspace root — `AGENTS.md`, `CLAUDE.md`, or what the assistant reads | never: the root is in no repository | no — recreate it per machine |
| The user's own assistant instructions | never | per tool |

Keep it to one paragraph: where `MEM.md` is, and that `mem-workspace` is active. Starting the agent from the
workspace root or from `private/` makes the pointer unnecessary.
