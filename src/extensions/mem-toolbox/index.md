# Extension: `mem-toolbox`

- **version**: 1.0.2
- **provides**: `TOOLS`, and the tool, library and runtime capability registry
- **subcommands**: `CHECK` — closed set
- **bootstrap entry**: `custom/installed/<host>.md` — see "Host files"
- **precedence**: **custom wins** — a project entry overrides a catalogue entry, and the override is disclosed
- **external actions**: yes — the approved package install in "Installing", and nothing else
- **default mode**: read-only

Records which tooling to use for a task — CLI tools, libraries, and the runtimes libraries need — and whether
it is actually available on the current host.

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
    index.md                runtimes, and domain -> sub-index
    index.<domain>.md       capability -> tool, one per domain
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

Lists the known tools with their capability, availability on this host, the agent environments, and stale or
`outdated` verifications. It does **not** re-probe: refreshing happens as a side effect of actually using a
tool, or on request through `MEM TOOLS CHECK`. Keeping this read-only is what avoids a second exception to the
read-only default.

## `MEM TOOLS CHECK`

- **mode**: may-write — `custom/installed/<current-host>.md` only
- **target**: none

Probes every `kind: runtime` entry and every agent environment recorded for this host, writes the results to
the host file, and reports what is missing or below its `min version`, with a proposal for each — see
"Installing" for what the proposal may contain.

It **must not** install, update, or reach the network: "below the minimum" is decided offline, against the
entry, never against "latest". It runs only when asked, never at session start. Its writes are the host-file
writes this extension already makes automatically, so it adds no new kind of write — only a moment to make them.

## Query before acting

Before performing an operation that needs a CLI tool or a library:

1. read `custom/index.md`, then `catalog/index.md` and the sub-index for the task's domain, **keyed by
   capability** — the lookup key is the task ("resize an image", "create a PDF"), which cannot be inferred from
   a filename such as `imagemagick.md`. A capability may have CLI and library candidates; they compete in one
   list, in preference order;
2. read `custom/installed/<current-host>.md` for the chosen candidate — the file exists, because it is the
   bootstrap entry; if it does not, create it first:
   - `confirmed` → use the recorded path and invocation. Re-probe first when the operation is destructive, or
     when the verification is old;
   - `unavailable` or `declined` → do **not** ask again. Offer the next candidate;
   - `outdated` → usable if it works; say it is below the minimum, once per session;
   - no section for this tool → probe, then record the result;
3. for a library, the same step applies to its runtime first, then to the library inside the agent environment
   — see "Libraries and runtimes";
4. no candidate in either catalogue → ask the user. If a tool is agreed on, write the custom entry, then the
   installed entry.

Verification recorded on **another host** is a hint about what to try, never proof. Say so when relying on it.

The agent **must never** install anything autonomously. Entries describe; the user authorises. The one
install the agent **may** perform is the approved one described in "Installing".

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
under it on its own initiative. It records where things are, and tells the user where a thing should go. The
one exception is `envs/`, and only with approval — see "Installing".

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

The convention is for **unpacked archives** only. A library has no folder of its own: it lives inside an agent
environment, and environments have their own location — see below.

## Libraries and runtimes

A library is used from a runtime, so it is looked up in two steps: the runtime, then the library inside the
runtime's agent environment.

| | Runtime (`kind: runtime`) | Library (`kind: library`) |
|---|---|---|
| Examples | `python`, `node` | `reportlab`, `pandas`, `svgo` |
| Declares | `min version` | `requires: <runtime id>`, `package`, `import` where it differs, `min version` |
| Probed by | its version flag, like a CLI tool | the environment's own runtime, below |
| Installed by | the user, always | the agent, with approval, into the dedicated environment only |

The library probe, run with the environment's interpreter rather than whichever is on `PATH`:

| Runtime | Probe |
|---|---|
| `python` | `python -c "import <import>"` succeeds, then `importlib.metadata.version("<package>")` gives the version |
| `node` | `npm ls --prefix <node env> <package> --depth=0 --json` |

Importing proves the library loads; the metadata version is the installed distribution's, which is what
`min version` is compared against. A module's `__version__` is not reliable: many do not define one.

`package` and `import` are separate fields because they differ more often than not — `Pillow` imports as
`PIL`, `python-docx` as `docx`. The **package** name is what an install takes and what an approval names.

A library whose runtime is missing or `unavailable` is not probed: report the runtime, not the library.

## Agent environments

The agent keeps **one environment per runtime, per host** — never one per project — and records it in the host
file as `<runtime> env`.

### The question, always asked

Which environment to use is the user's decision. The agent **must** ask it the first time a runtime is needed on
a host, **must not** preset or infer an answer, and **must** state the trade-offs every time it asks:

| | `dedicated` | `system` |
|---|---|---|
| Every project on this host shares the same tools and versions | **yes** | **yes** |
| Isolated from the OS and from other software | yes | no — shared with every program using that interpreter |
| Needs admin rights | no | often |
| Undone by | deleting one folder | uninstalling package by package |
| The agent may install into it, with approval | yes | no — it proposes, the user runs |
| Survives an interpreter upgrade | the folder remains; rebuild it for a new `X.Y` | packages may be dropped with the old interpreter |
| Costs | one more directory, invoked through its own interpreter path | none to create; a Python marked *externally managed* ([PEP 668](https://peps.python.org/pep-0668/)) refuses `pip install` outright |

The first row is deliberately the same in both columns: sharing across projects comes from having **one
environment per host**, not from choosing the system interpreter. What neither gives is the same versions on
**another** host — that is what `min version` in the entry is for.

The answer is recorded and not re-asked on that host. Every install approval restates it in one line, so the
choice stays visible.

### Where a dedicated environment lives

```text
<tools root>/
  envs/
    python-<X.Y>/           a venv, bound to one interpreter version
    node/                   an npm --prefix directory; executables in node_modules/.bin/
```

The interpreter version belongs in the Python name because a venv cannot outlive the `X.Y` that created it; a
new interpreter means a sibling folder, not an edit. With `tools root: none`, the agent asks where the
environment should live, and **may** propose a location under `%LOCALAPPDATA%` or `$HOME`.

Creating the dedicated environment is itself an install, and needs the same approval.

## Installing

Two levels, separated by whether the change can be undone by deleting one folder:

| Target | The agent |
|---|---|
| A package into the **dedicated** environment, or creating that environment | **may** run the install, after explicit approval |
| A runtime, a CLI tool, or a package into a **system** interpreter | **must** only propose: the exact command or destination, run by the user |

An approval **must** name the package, the version or constraint, the environment, and the registry, and say
that installing a package runs its code. The package name **must** be one written in a catalogue entry's
`package` field, or given verbatim by the user: an install takes a name and executes what it finds, so a
misspelt name is an execution, not a typo. Ask once per package per session; a refusal is recorded as
`declined`.

An install downloads from a registry and writes outside the repository, so it is an **external action** in
the core's sense. The approval above is required **even when** `extensions_allow_external_side_effects` is
true: that option waives confirmation for external actions in general, and this one executes third-party code.

After an install the agent probes the package and records the result like any other observation.

An entry still never carries an install command. The command appears in the approval, and nowhere else.

### `outdated`

An entry **may** declare a `min version`. A probe below it records `outdated`: the tool stays usable, and the
agent says once per session that it is below the minimum, with a proposal at the level above. A refused update
is recorded as `update declined: <date>` in that section, and **must not** be proposed again until the user
asks.

## Boundary with `references/` and with project dependencies

`references/` holds project facts: dependencies, canonical URLs, useful commands. This extension holds
**capability state**. If the question is *"may I run this, and how"*, it belongs here.

A library the **product** depends on — declared in `requirements.txt`, `pyproject.toml`, `package.json` — is a
project fact, not agent tooling. It belongs to the project's own manifest and to `references/`, and the agent
**must not** install it into an agent environment as a substitute for the project's own setup.
