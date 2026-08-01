# Extension: `mem-toolbox`

- **version**: 1.0.0
- **provides**: `TOOLS`, and the CLI capability registry
- **precedence**: **custom wins** — a project entry overrides a catalogue entry, and the override is disclosed
- **external actions**: no
- **default mode**: read-only

Records which CLI tooling to use for a task, and whether it is actually available on the current host.

## Precedence

Custom wins. This is the **opposite** of `mem-commands`, deliberately: a catalogue entry is reference data, and
a local entry is by definition closer to the truth about this project and this machine. Overriding is a
correction, not a hijack.

When a custom entry overrides a catalogue one, say so the first time it is used in a session. Do not harmonise
the two directions: each extension declares its own.

## Three catalogues, two layers

| # | Catalogue | Answers | Layer |
|---|---|---|---|
| 1 | `catalog/` | which tool to use for a task | base — distributed, in the manifest |
| 2 | `custom/tools/` | which tool **this project** uses | custom |
| 3 | `custom/installed/` | what exists **on this host**, and where | custom |

```text
extensions/mem-toolbox/
  index.md                  this file
  TOOL.template.md          entry schema
  catalog/
    index.md                capability -> tool
    <tool>.md
  custom/                   never distributed, never in the manifest
    index.md                capability -> tool, project-local
    tools/<tool>.md
    installed/<host>.md
```

The third catalogue is what makes the other two safe. The knowledge base is committed and shared, so recording
"this tool is available" as a plain fact would mislead every other machine — an agent elsewhere would read it and
**skip asking the user**. Availability therefore lives in its own per-host files and never inside a catalogue
entry.

`custom/` does not exist until the first entry is written. Its absence is normal.

## `MEM TOOLS`

- **mode**: read-only
- **target**: none

Lists the known tools with their capability, availability on this host, and stale verifications. It does **not**
re-probe: refreshing happens as a side effect of actually using a tool. Keeping this read-only is what avoids a
second exception to the read-only default.

## Query before acting

Before performing an operation that needs a CLI tool:

1. read `custom/index.md`, then `catalog/index.md`, **keyed by capability** — the lookup key is the task
   ("resize an image", "render an SVG"), which cannot be inferred from a filename such as `imagemagick.md`;
2. read `custom/installed/<current-host>.md` for the chosen candidate:
   - `confirmed` → use the recorded path and invocation. Re-probe first when the operation is destructive, or
     when the verification is old;
   - `unavailable` or `declined` → do **not** ask again. Offer the next candidate;
   - no entry for this host → probe, then record the result;
3. no candidate in either catalogue → ask the user. If a tool is agreed on, write the custom entry, then the
   installed entry.

Verification recorded on **another host** is a hint about what to try, never proof. Say so when relying on it.

The agent **must never** install a tool autonomously. Entries describe; the user authorises.

## Writing entries

| What | Trigger |
|---|---|
| `custom/installed/<host>.md` | **Automatic.** It records an observation — a version command answered — it is local, and it is precisely the data that avoids re-probing every session |
| `custom/tools/<tool>.md` | **Confirmation required.** "This is what we use for X" is an editorial judgement, not an observation |

Record absence as well as presence. `unavailable` and `declined` are persistent answers; without them the agent
re-probes and re-asks every session.

An installed entry **must** reference a catalogue entry by id. If the tool is in neither catalogue, write the
custom entry first, otherwise the host layer degenerates into an undocumented list of paths.

## Host files

One file per host, never a shared list: a shared file produces merge conflicts and lets one machine's reality
overwrite another's. A colleague's machine adds a file instead of editing yours.

The host key is a hostname or a label of the user's choosing. This is the only place the knowledge base records
machine identity, which is why the next rule matters.

**Paths leak.** `C:\Users\<name>\...` exposes a username, and a tools directory exposes internal layout, into a
repository that is normally committed. Therefore:

- prefer environment-relative forms — `%LOCALAPPDATA%`, `%PROGRAMFILES%`, `$HOME` — wherever they resolve;
- a label may replace a hostname;
- `custom/installed/` is committed by default, because "on Windows hosts we use vips at this path" is useful team
  knowledge. A project that does not want host facts in its history may gitignore that folder alone: the
  catalogues stay versioned.

Never record a credential. A tool needing an auth token documents the variable **name**, never its value.

## Boundary with `references/`

`references/` holds project facts: dependencies, canonical URLs, useful commands. This extension holds
**capability state**. If the question is *"may I run this, and how"*, it belongs here.
