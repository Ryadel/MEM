# Extension: `mem-toolbox`

- **version**: 1.0.3
- **provides**: `TOOLS`, and the tool, library and runtime capability registry
- **subcommands**: `CHECK`, `SETUP` — closed set
- **precedence**: **custom wins** — a project entry overrides a catalogue entry, and the override is disclosed
- **external actions**: yes — writing this host's machine file under `~/.mem/mem-toolbox/` once the user has
  confirmed it, and the approved package install in "Installing"; nothing else
- **configuration**: `extensions_mem_toolbox_kb_copy` (default `false`) — see "Copy in the knowledge base"
- **default mode**: read-only

Records which tooling to use for a task — CLI tools, libraries, and the runtimes libraries need — and whether
it is actually available on the current host.

## Precedence

Custom wins. This is the **opposite** of `mem-commands`, deliberately: a catalogue entry is reference data, and
a local entry is by definition closer to the truth about this project and this machine. Overriding is a
correction, not a hijack.

When a custom entry overrides a catalogue one, say so the first time it is used in a session. Do not harmonise
the two directions: each extension declares its own.

## Three catalogues, two places

| # | Catalogue | Answers | Lives in |
|---|---|---|---|
| 1 | `catalog/` | which tool to use for a task | the knowledge base — base layer, distributed in the manifest |
| 2 | `custom/tools/` | which tool **this project** uses | the knowledge base — custom layer |
| 3 | the **machine file** | what exists **on this host**, and where | `~/.mem/mem-toolbox/host.md`, outside every repository |

```text
extensions/mem-toolbox/        in the knowledge base
  index.md                     this file
  TOOL.template.md             entry schemas
  catalog/
    index.md                   runtimes, and domain -> sub-index
    index.<domain>.md          capability -> tool, one per domain
    <tool>.md
  custom/                      never distributed, never in the manifest
    index.md                   capability -> tool, project-local
    tools/<tool>.md
    installed/<host>.md        optional copy of a machine file — see "Copy in the knowledge base"

~/.mem/mem-toolbox/            per user, per host (%USERPROFILE%\.mem\mem-toolbox\ on Windows)
  host.md                      this host: tools root, agent environments, one section per tool
```

The first two catalogues are about the project and travel with it. The third is about the machine, so it lives on
the machine: **one file per host, shared by every project on that host**. The tools root is asked once per host,
an agent environment is chosen once per host, and a tool probed while working on one project is known in all the
others. `~/.mem/` is the per-user folder MEM extensions use for machine state; `mem-stats` keeps its ledger there
too.

Availability never goes inside a catalogue entry. The knowledge base is committed and shared, so recording "this
tool is available" as a plain fact would mislead every other machine — an agent elsewhere would read it and **skip
asking the user**.

`custom/tools/` does not exist until the first entry is written. Its absence is normal.

## `MEM TOOLS`

- **mode**: read-only
- **target**: none

Lists the known tools with their capability, availability on this host, the agent environments, and stale or
`outdated` verifications, from the machine file. It does **not** re-probe: refreshing happens as a side effect of
actually using a tool, or on request through `MEM TOOLS CHECK`. Without a machine file it says so and proposes
`MEM TOOLS SETUP`.

## `MEM TOOLS CHECK`

- **mode**: may-write — the machine file, and the knowledge base copy when it is enabled
- **target**: none

Probes every `kind: runtime` entry and every agent environment recorded for this host, writes the results to
the machine file, and reports what is missing or below its `min version`, with a proposal for each — see
"Installing" for what the proposal may contain.

It **must not** install, update, or reach the network: "below the minimum" is decided offline, against the
entry, never against "latest". It runs only when asked, never at session start. Its writes are the machine-file
writes this extension already makes automatically, so it adds no new kind of write — only a moment to make them.

## `MEM TOOLS SETUP`

- **mode**: may-write — the machine file; `MEM.config.md` and the knowledge base copy only when the user chooses
  the copy
- **target**: none

The wizard for the machine file. Ask with the client's question tool when it has one (numbered questions
otherwise), recommended option first, in the user's language, explaining each choice plainly. Write nothing
before the final confirmation.

1. **Tools root** — where portable tools live on this host. See "The tools root" for the valid answers and for
   what may be proposed.
2. **Agent environments** — for each `kind: runtime` entry (`python`, `node`): `dedicated`, `system`, or *decide at
   first need*. State the trade-offs in "The question, always asked"; nothing is preselected.
3. **Copy in this knowledge base** — no (recommended) · yes. It is a property of the repository, not of the
   machine — see "Copy in the knowledge base". It is asked only here: elsewhere an unset option means `false`, and
   no project is ever asked about it unprompted.

Then show the plan: the path and full content of the machine file, and, when the copy is chosen, the
`MEM.config.md` line and the copy's path. One confirmation writes all of it. That confirmation is the user's
approval for this extension to keep its machine file: later automatic writes — the observations in "Writing
entries" — go to that one file only.

When a machine file already exists, its values are the defaults shown, tool sections are kept, and nothing is
re-probed. Run `SETUP` again to change an answer. When there is no machine file but this knowledge base holds a
host file for this host, `SETUP` starts from it — see "Existing host files".

If the client cannot write outside the repository — a sandbox, a refused permission — say so and show the file's
content and path for the user to save. **Never** fall back silently to writing it into the repository.

## Query before acting

Before performing an operation that needs a CLI tool or a library:

1. read `custom/index.md`, then `catalog/index.md` and the sub-index for the task's domain, **keyed by
   capability** — the lookup key is the task ("resize an image", "create a PDF"), which cannot be inferred from
   a filename such as `imagemagick.md`. A capability may have CLI and library candidates; they compete in one
   list, in preference order;
2. read the machine file for the chosen candidate. If there is none on this host, create it first, **before** any
   tool is looked up: import it as "Existing host files" describes when this knowledge base holds a host file for
   this host, otherwise run `MEM TOOLS SETUP` — or, when the user would rather not, ask the tools root question
   alone and write the file with it after the same single confirmation. Then:
   - `confirmed` → use the recorded path and invocation. Re-probe first when the operation is destructive, or
     when the verification is old;
   - `unavailable` or `declined` → do **not** ask again. Offer the next candidate;
   - `outdated` → usable if it works; say it is below the minimum, once per session;
   - no section for this tool → probe, then record the result;
3. for a library, the same step applies to its runtime first, then to the library inside the agent environment
   — see "Libraries and runtimes";
4. no candidate in either catalogue → ask the user. If a tool is agreed on, write the custom entry, then the
   installed entry.

Once the machine file exists, its questions are **never asked again on that host**, from any project.

A host file in the knowledge base for **another host** is a hint about what to try, never proof. Say so when
relying on it.

The agent **must never** install anything autonomously. Entries describe; the user authorises. The one
install the agent **may** perform is the approved one described in "Installing".

## Writing entries

| What | Trigger |
|---|---|
| The machine file | Created by `MEM TOOLS SETUP` or at first need, after one confirmation. From then on **automatic**: each write records an observation — a version command answered — it is local, and it is precisely the data that avoids re-probing every session |
| `custom/installed/<host>.md` | **Automatic** when `extensions_mem_toolbox_kb_copy` is true: rewritten from the machine file after each write to it |
| `custom/tools/<tool>.md` | **Confirmation required.** "This is what we use for X" is an editorial judgement, not an observation |

Record absence as well as presence. `unavailable` and `declined` are persistent answers; without them the agent
re-probes and re-asks every session.

An installed entry **must** reference a catalogue entry by id. If the tool is in neither catalogue, write the
custom entry first, otherwise the host layer degenerates into an undocumented list of paths.

## The machine file

`~/.mem/mem-toolbox/host.md` — `%USERPROFILE%\.mem\mem-toolbox\host.md` on Windows. Its schema is the installed
entry in `TOOL.template.md`: a header with the host name, the OS, the tools root and the agent environments, then
one section per tool. It is per user and per host, and it is in no repository, so it never produces a merge
conflict and one machine's reality never overwrites another's.

### Created first, not on demand

The file is created **before** any tool is looked up, even when it has nothing to say yet. A path has to be
recorded the moment a tool is first used, which is exactly when no file exists to hold it; an agent under time
pressure then puts it wherever it can — a catalogue entry, `references/`, a daily log — and the separation this
extension exists to enforce is broken on first contact. An empty machine file costs nothing and removes the
decision.

A header with no tool sections is a meaningful state: "this host is known, nothing probed yet". It is not the same
as a missing file, which means "this host has never been set up".

### The tools root

**Where do portable tools live on this host?** Recorded as `tools root`, asked **once per host**.

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

Per-tool paths are written relative to the tools root, so a whole toolchain can be relocated by editing one line.
The machine file is never committed, so its paths may be absolute; it never records a credential. A tool needing
an auth token documents the variable **name**, never its value.

### Copy in the knowledge base

`extensions_mem_toolbox_kb_copy` in `MEM.config.md`, default **`false`**. When `true`, every write to the machine
file is mirrored into this knowledge base as `custom/installed/<host>.md`, so "on Windows hosts we use vips at this
path" becomes team knowledge that survives the machine.

- The copy is a **mirror**, never the source: on its own host the machine file is authoritative, and a copy from
  another host is a hint.
- The host key is the hostname or a label of the user's choosing; it is the only place the knowledge base records
  machine identity.
- **Paths leak.** `C:\Users\<name>\...` exposes a username, and a tools directory exposes internal layout, into a
  repository that is normally committed. In the copy, prefer environment-relative forms — `%LOCALAPPDATA%`,
  `%PROGRAMFILES%`, `$HOME` — and keep per-tool paths relative to the tools root.
- Turning it on changes `MEM.config.md`, so it needs confirmation; `SETUP` asks. Turning it off leaves the existing
  copy where it is: say that it is no longer updated, and remove it only if the user asks.

The default is `false` because the copy is the only part of this extension that writes machine facts into a
repository, and most projects do not need them there.

### Existing host files

A knowledge base may already hold `custom/installed/<host>.md` for the current host, written when host data lived
there. When the machine file is missing and such a file exists — matched by hostname or by a label the user
recognises; ask which when several could be this host — the agent **must** propose importing it into the machine
file with **one** confirmation, and **must not** ask the tools root or environment questions again. Import the
header — host name, OS, tools root, the `<runtime> env` lines — and every tool section; drop the old
`source control` field.

The file in the knowledge base is left in place. Say what it becomes: with `extensions_mem_toolbox_kb_copy: true`,
the maintained copy; otherwise a snapshot no longer updated, which the user may keep or remove.

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
result in the machine file.

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

The agent keeps **one environment per runtime, per host** — never one per project — and records it in the machine
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
