# Extension: `mem-toolbox`

- **version**: 1.0.1
- **provides**: `TOOLS`, and the CLI capability registry
- **bootstrap entry**: `custom/installed/<host>.md` — see "Host files"
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

`custom/tools/` does not exist until the first entry is written. Its absence is normal. `custom/installed/<host>.md` is the exception: it is this extension's **bootstrap entry** and is created before it has anything to say.

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
2. read `custom/installed/<current-host>.md` for the chosen candidate — the file exists, because it is the
   bootstrap entry; if it does not, create it first:
   - `confirmed` → use the recorded path and invocation. Re-probe first when the operation is destructive, or
     when the verification is old;
   - `unavailable` or `declined` → do **not** ask again. Offer the next candidate;
   - no section for this tool → probe, then record the result;
3. no candidate in either catalogue → ask the user. If a tool is agreed on, write the custom entry, then the
   installed entry.

Verification recorded on **another host** is a hint about what to try, never proof. Say so when relying on it.

The agent **must never** install a tool autonomously. Entries describe; the user authorises.

## Writing entries

| What | Trigger |
|---|---|
| `custom/installed/<host>.md` | **Automatic**, and created at install before it holds anything. It records an observation — a version command answered — it is local, and it is precisely the data that avoids re-probing every session |
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

### Created first, not on demand

`custom/installed/<host>.md` is this extension's **bootstrap entry**. It **must** be written at installation,
and on any host where it is missing, **before** any tool is looked up — with the host name, the OS, the tools
root, and no tool sections.

Lazy creation was the earlier behaviour and it was the wrong default here. A path has to be recorded the moment
a tool is first used, which is exactly when no file exists to hold it; an agent under time pressure then puts it
wherever it can — a catalogue entry, `references/`, a daily log — and the layer separation this extension exists
to enforce is broken on first contact. An empty host file costs nothing and removes the decision.

An empty file is a meaningful state: "this host is known, nothing probed yet". It is not the same as a missing
file, which means "this host has never been seen".

### The two questions asked at installation

Creating the bootstrap entry means answering two things, and both are asked **once**, at installation, then
recorded in the file. Neither is re-asked per session; on a new host only the first is asked again, because the
second belongs to the project rather than to the machine.

**1. Where do portable tools live on this host?** Recorded as `tools root`.

The agent **must** ask rather than guess. It **may** propose a value it has evidence for — a directory already
holding one of the catalogue's tools, or one named in `PATH` — and **must** show that evidence when it does.

Three answers are valid:

| Answer | Meaning |
|---|---|
| a directory | Portable tools are unpacked there, laid out as described in "Where tools live on disk" |
| `none` | Everything comes from platform installers or a package manager; there is no directory to own |
| a directory that does not exist yet | Recorded as intended. The agent **must not** create it: an empty folder implies an install that has not been authorised |

`none` is a complete answer, not a refusal. Record it and write absolute or environment-relative paths per tool.

This value is what lets a proposal be specific. When a capability has no available tool, the agent proposes a
tool and names **the exact directory the archive should be unpacked into**, derived from the root and the
convention below. Naming the destination is the whole benefit of asking; it is not permission to write there.

**The tools root does not make the agent an installer.** It never downloads, unpacks, moves or deletes anything
under it on its own initiative. It records where things are, and tells the user where a thing should go.

**2. Is `custom/installed/` kept under source control?** Recorded as `source control`. **The default is yes.**

"On Windows hosts we use vips at this path" is useful team knowledge, and the whole point of a knowledge base is
that it survives the machine that produced it.

If the answer is no, the agent **must** add an ignore rule for that folder alone — never for the extension, and
never for `custom/` as a whole, which would also discard `custom/tools/`. Say plainly what that costs: the host
data then exists in no repository, so it is lost with the machine and unavailable to anyone else. That is
acceptable here only because the data is re-derivable by probing. Treat a missing file as normal, never as an
anomaly.

**Paths leak.** `C:\Users\<name>\...` exposes a username, and a tools directory exposes internal layout, into a
repository that is normally committed. Therefore:

- prefer environment-relative forms — `%LOCALAPPDATA%`, `%PROGRAMFILES%`, `$HOME` — wherever they resolve;
- a label may replace a hostname;
- record the tools root once, at the top of the host file, and write per-tool paths relative to it.

Never record a credential. A tool needing an auth token documents the variable **name**, never its value.

## Where tools live on disk

A portable tool is an archive someone unpacked. Left alone, its folder is named after the archive —
`oxipng-10.1.1-x86_64-pc-windows-msvc`, `vips-dev-8.18`, `ffmpeg-9.0.1-essentials_build` — which buries the one
thing you scan for, the tool's name, behind a prefix and under a version you did not ask about.

The convention is two segments:

```text
<tools root>/
  <tool-id>/
    <version>[-<variant>][-<target>]/
```

| Unpacked as | Becomes |
|---|---|
| `oxipng-10.1.1-x86_64-pc-windows-msvc` | `oxipng/10.1.1-x86_64-pc-windows-msvc` |
| `vips-dev-8.18` | `vips/8.18-dev` |
| `realesrgan-ncnn-vulkan-v0.2.0-windows` | `realesrgan/v0.2.0-ncnn-vulkan-windows` |
| `ffmpeg-9.0.1-essentials_build` | `ffmpeg/9.0.1-essentials` |

Three rules make it mechanical:

1. **The first segment is the tool id**, spelled exactly as the catalogue entry filename. The folder name is
   then the lookup key: a directory listing maps onto catalogue entries without guessing.
2. **The version leads the second segment**, so builds of one tool sort in version order.
3. **Everything that varies per build stays in the second segment** — target triple, build flavour, and the
   implementation when a tool has more than one. `realesrgan` is the tool; `ncnn-vulkan` is one implementation
   of it, and a Python one would be a sibling folder rather than an unrelated root.

Two consequences worth stating. Several versions of one tool coexist without colliding, which is what makes a
version-pinned entry meaningful. And an upgrade adds a folder instead of overwriting one, so a rollback is a
path change rather than a re-download.

The agent **must not** reorganise a tools directory on its own initiative: it is the user's filesystem, outside
the repository, and the layout may be load-bearing for a `PATH` entry or a shortcut. Propose it, name every
folder that would move, and check `PATH` first. As always, the agent **must never** install a tool
autonomously — this convention describes where an install *should land*, never that one may happen.

Combined with the recorded `tools root`, the convention makes a proposal concrete. Instead of "you could install
ffmpeg", the agent can say which directory to unpack the archive into:

```text
<tools root>/ffmpeg/9.0.1-essentials/
```

That is a sentence in a proposal, not an action. The user unpacks it; the agent then probes, and records the
result in the host file.

## Boundary with `references/`

`references/` holds project facts: dependencies, canonical URLs, useful commands. This extension holds
**capability state**. If the question is *"may I run this, and how"*, it belongs here.
