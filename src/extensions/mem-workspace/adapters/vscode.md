# Adapter: VS Code

One multi-root workspace file in `private/` that opens every repository of the workspace in one window.

## The workspace file

`private/<project>.code-workspace`:

```json
{
  "folders": [
    { "name": "private", "path": "." },
    { "name": "public", "path": "../public" },
    { "name": "wiki", "path": "../wiki" }
  ]
}
```

- Each folder is a repository, so the Source Control view lists each one separately, with its own branch,
  changes and commit box. Nothing else is needed to commit any of them from the window.
- Folder paths are relative to the file. Folder names and adjacency are load-bearing, which is why
  `MEM WORKSPACE INIT` records them.
- The file lives in `private/` and is committed there. It **must not** be placed in a public repository: it names
  the private folder.
- Settings that apply to one repository go in that repository's own `.vscode/settings.json`; settings in the
  workspace file apply to all of them and are private.

An agent started from this window may be rooted at the first folder. Listing `private` first keeps `KB_ROOT` in
view.

## Check

Added to `MEM WORKSPACE CHECK` as check 14 when `custom/workspace.md` names this adapter:

- every `folders[].path` in the workspace file resolves to an existing folder — error otherwise;
- every role in `custom/workspace.md` appears among the folders — warning otherwise.
