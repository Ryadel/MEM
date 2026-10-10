# Workspace file template

Copy into `custom/workspace.md`, or let `MEM WORKSPACE INIT` write it. Paths are relative to the workspace root,
which is the parent of the private repository; never write an absolute path here.

```markdown
# Workspace

## Roles

| Role | Folder | Remote | Visibility | Branch |
|---|---|---|---|---|
| public | public | https://github.com/<owner>/<project>.git | public | main |
| private | private | https://github.com/<owner>/<project>.Dev.git | private | main |
| wiki | wiki | https://github.com/<owner>/<project>.wiki.git | public | master |

Visibility: recorded, not verified.

## Push order

public, wiki, private

## Forbidden in public

Patterns added to the defaults in `check.md`, one per line, or "none".

## Exceptions

| Path in public | Check | Reason |
|---|---|---|

## Adapter

none | visual-studio: private/<project>.Dev.slnx | vscode: private/<project>.code-workspace
```

- **Roles**: exactly one `private`, at least one `public`, at most one `wiki`. Delete the `wiki` row when there is
  none.
- **Branch**: a GitHub wiki uses `master` and cannot rename it. Do not "fix" it.
- **Exceptions**: one row per path and per check, with a reason a reviewer can judge. Leave the table empty rather
  than writing a broad exception.
