# `MEM WORKSPACE CHECK`

- **mode**: read-only
- **target**: none
- **runs**: read-only local `git` only — see [index.md](index.md), "Commands it runs"

Verifies the invariants in [index.md](index.md) against the instance described in `custom/workspace.md`.

If `custom/workspace.md` is missing, report it and stop: propose `MEM WORKSPACE INIT`. Never guess the roles.

## Notation

`<root>` is the workspace root, `<private>` the private role's folder, `<public>` each public role's folder (run
the public checks once per public repository), `<wiki>` the wiki's. `<kb>` is `KB_ROOT` relative to `<root>`.

**KB pathspecs** — the files that identify a MEM knowledge base:

```text
:(glob)**/MEM.md  :(glob)**/MEM.config.md  :(glob)**/MEM.index.md  :(glob)**/MEM.project.md
:(glob)**/MEM.remote-cache.md  :(glob)**/extensions/EXT.md
```

Append `:(exclude)<path>` for every exception in `custom/workspace.md` that names the check being run.

**Forbidden patterns** — strings that resolve to the private repository:

- `<owner>/<repo>` of the private remote;
- `../<private>/`;
- `<kb>`;
- every extra pattern in `custom/workspace.md`.

Do **not** search for the bare folder name: `private` is an ordinary English word, and the noise would bury the
real findings.

Ignore-pattern lines in a public `.gitignore` are the safety net that check 10 looks for, and naming the private
folder or the dev solution is their job: they are not hits. Comments in the same file are.

## Checks

| # | Check | How | Fails as |
|---|---|---|---|
| 1 | Workspace root is not a repository | `git -C <root> rev-parse --git-dir` exits non-zero | error |
| 2 | Each role folder is a repository top level | `git -C <folder> rev-parse --show-toplevel` equals the folder | error |
| 3 | No role folder inside another | compare the paths of 2 | error |
| 4 | Remotes match the record | `git -C <folder> remote get-url origin` equals `custom/workspace.md` | error |
| 5 | `KB_ROOT` is tracked in `<private>` | `git -C <private> ls-files --error-unmatch <KB_ROOT>/MEM.md` succeeds | error if in another repository; warning if untracked |
| 6 | No KB file tracked in `<public>` | `git -C <public> ls-files -- <KB pathspecs>` is empty | error |
| 7 | No KB file about to be added to `<public>` | `git -C <public> ls-files --others --exclude-standard -- <KB pathspecs>` is empty | error |
| 8 | `<public>` does not reference `<private>` | `git -C <public> grep -n -I -i -F --untracked -e <pattern>...` is empty | error |
| 9 | No KB file in `<public>` history | `git -C <public> log --all --format="%h %ad %s" --date=short -- <KB pathspecs>` is empty | warning |
| 10 | Safety net present | `git -C <public> check-ignore -q <private>/probe` succeeds | warning |
| 11 | Wiki not ignored | `git -C <public> check-ignore -q <wiki>/probe` fails | warning |
| 12 | Wiki pages linked by absolute URL | see below | warning |
| 13 | Visibility as recorded | not verifiable offline | info, always |
| 14 | Adapter checks | per the adapter named in `custom/workspace.md` | as the adapter says |

Notes on the checks that need judgement:

- **5** — "in another repository" means `KB_ROOT` resolves to a public role's folder. That is the failure this
  extension exists to prevent.
- **8** — report each hit with its file and line. A hit inside a quoted example is still a hit; exempt it in
  `custom/workspace.md` with a reason, rather than dismissing it in the report.
- **9** — removing files from the tree does not remove them from history: everything shown is still public, in
  every existing clone. Say so. Rewriting history is the user's decision, and it is destructive. This extension
  **must not** propose a command that rewrites history or force-pushes; it states the fact. If any of those files
  held a secret, the secret is to be treated as disclosed.
- **10** — guards against a private folder being copied *into* a public repository. A warning, not an error:
  this line is the second layer, never the privacy mechanism.
- **11** — documentation is publishable. If a wiki folder ever appears inside the public repository it should show
  up in `git status`, not go silent.
- **12** — only with a `wiki` role. List the page names with `git -C <wiki> ls-files "*.md"`, then search
  `<public>` for relative links to them (`](<Page>.md`, `](<Page>)`). A wiki is a separate repository, so a
  relative link to it is already broken on the public site.

Skip a check only when its role does not exist, and report it as `n/a`.

## Report

```markdown
> MEM WORKSPACE CHECK: active (mem-workspace 1.0.0)

| # | Check | Result | Finding |
|---|---|---|---|
| 1 | Workspace root is not a repository | pass | |
| 8 | public/ does not reference private/ | error | `docs/setup.md:12` links into the private repository |

**Verdict**: PASS | PASS WITH WARNINGS | FAIL

**Exceptions in effect**: <path> — <check> — <reason>, one per line, or "none".

**Not verified**: repository visibility (offline).
```

`FAIL` when any error is reported. The check reports and stops: it **must not** fix a finding, edit an ignore
file, or move a file. Propose the fix; the user decides.
