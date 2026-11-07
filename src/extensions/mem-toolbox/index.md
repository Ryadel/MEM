# Extension: `mem-toolbox`

- **version**: 1.1.0
- **provides**: `TOOLS`, and the tool, library and runtime capability registry
- **subcommands**: `CHECK`, `SETUP` — closed set
- **precedence**: **custom wins** — a project entry overrides a catalogue entry, and the override is disclosed
- **external actions**: yes — writing tool sections and summary rows in the core's machine file,
  `~/.mem/hosts/<hostname>/machine.md`, and the approved package install in "Installing"; nothing else
- **configuration**: none. `extensions_mem_toolbox_kb_copy` was retired in 1.1.0 — see "Legacy host files"
- **upgrade**: `UPGRADE.md`
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
| 2 | `custom/tools/` | which tool **this project** uses, and what it **requires** | the knowledge base — custom layer |
| 3 | the **machine file** | what exists **on this machine**, and where | the core's machine base, `~/.mem/hosts/<hostname>/machine.md`, outside every repository |

```text
extensions/mem-toolbox/        in the knowledge base
  index.md                     this file
  TOOL.template.md             entry schemas
  UPGRADE.md                   migration steps for this extension
  catalog/
    index.md                   runtimes, and domain -> sub-index
    index.<domain>.md          capability -> tool, one per domain
    <tool>.md
  custom/                      never distributed, never in the manifest
    index.md                   capability -> tool, project-local
    tools/<tool>.md

~/.mem/hosts/<hostname>/       the core's machine base (%USERPROFILE%\.mem\hosts\<hostname>\ on Windows)
  machine.md                   summary (with this extension's tools root and environment rows), one section per tool
```

The first two catalogues are about the project and travel with it. The third is about the machine, so it lives on
the machine: **one file per machine and OS account, shared by every project on it**. It belongs to the core — see
`MEM.md`, "Machine base" — so every project reads it, with or without this extension; this extension adds the tools
root, the agent environments, and one section per tool. The tools root is asked once per machine, an agent
environment is chosen once per machine, and a tool probed while working on one project is known in all the others.

Availability never goes inside a catalogue entry. The knowledge base is committed and shared, so recording "this
tool is available" as a plain fact would mislead every other machine — an agent elsewhere would read it and **skip
asking the user**. A project states what it **requires** (`min version` in its custom entry); the machine file states
what is there.

`custom/tools/` does not exist until the first entry is written. Its absence is normal.

## `MEM TOOLS`

- **mode**: read-only
- **target**: none

Lists the known tools with their capability, what the machine file observed on this machine, the agent
environments, expired observations, and — against this project's entries — versions below a `min version`. It does
**not** re-probe: refreshing happens as a side effect of actually using a tool, or on request through
`MEM TOOLS CHECK`. Without a machine file it says so.

## `MEM TOOLS CHECK`

- **mode**: may-write — the machine file
- **target**: none

Probes every `kind: runtime` entry and every agent environment recorded for this machine, writes the observations
to the machine file, and reports what is not found or below the `min version` of this project's effective entry
(custom over catalogue), with a proposal for each — see "Installing" for what the proposal may contain.

It **must not** install, update, or reach the network: "below the minimum" is decided offline, against the
entry, never against "latest". It runs only when asked, never at session start. Its writes are the machine-file
writes this extension already makes automatically, so it adds no new kind of write — only a moment to make them.

## `MEM TOOLS SETUP`

- **mode**: may-write — the machine file
- **target**: none

The optional wizard for this extension's rows of the machine file. Ask with the client's question tool when it has
one (numbered questions otherwise), recommended option first, in the user's language, explaining each choice
plainly. Write nothing before the final confirmation.

1. **Tools root** — where portable tools live on this machine. See "The tools root" for the valid answers and for
   what may be proposed.
2. **Agent environments** — for each `kind: runtime` entry (`python`, `node`): `dedicated`, `system`, or *decide at
   first need*. State the trade-offs in "The question, always asked"; nothing is preselected.

Then show the plan: the summary rows to write. One confirmation writes them. That confirmation is the user's approval
for this extension to keep its rows and sections in the machine file: later automatic writes — the observations in
"Writing entries" — go to that one file only.

When the rows already exist, their values are the defaults shown, tool sections are kept, and nothing is re-probed.
Run `SETUP` again to change an answer. Nobody has to run `SETUP`: without it, the tools root and each environment are
asked the first time they are actually needed.

If the client cannot write outside the repository — a sandbox, a refused permission — say so and show the rows and
the path for the user to save. **Never** fall back silently to writing them into the repository.

## Query before acting

Before performing an operation that needs a CLI tool or a library:

1. read `custom/index.md`, then `catalog/index.md` and the sub-index for the task's domain, **keyed by
   capability** — the lookup key is the task ("resize an image", "create a PDF"), which cannot be inferred from
   a filename such as `imagemagick.md`. A capability may have CLI and library candidates; they compete in one
   list, in preference order;
2. read the machine file's section for the chosen candidate (the core has already read the summary). If the machine
   file does not exist yet, the core creates it — see `MEM.md`, "Machine base". Then:
   - `confirmed` → use the recorded path and invocation. Re-probe first when the operation is destructive, or
     when the verification is old. If the observed version is below the `min version` of this project's effective
     entry, it is still usable if it works: say so once per session;
   - `declined` → do **not** ask again. Offer the next candidate;
   - `not found` → an observation, not a verdict: re-probe once — always when it is older than 30 days, and before
     telling the user the tool is missing — then offer the next candidate;
   - no section for this tool → probe, then record the result;
3. for a library, the same step applies to its runtime first, then to the library inside the agent environment
   — see "Libraries and runtimes";
4. no candidate in either catalogue → ask the user. If a tool is agreed on, write the custom entry, then the
   installed entry.

Once recorded, the tools root and environment answers are **never asked again on that machine**, from any project.

A host file in a knowledge base, or another machine's tree in a synced `~/.mem/`, is a hint about what to try, never
proof. Say so when relying on it.

The agent **must never** install anything autonomously. Entries describe; the user authorises. The one
install the agent **may** perform is the approved one described in "Installing".

## Writing entries

| What | Trigger |
|---|---|
| Tool sections and observations in the machine file | **Automatic**: each write records an observation — a version command answered — it is local, and it is precisely the data that avoids re-probing every session. Written with the script in `MEM.md`, "Writing shared files", mode `section`; only what is new or changed |
| Tools root and environment rows | After the user's answer, mode `row` |
| `custom/tools/<tool>.md` | **Confirmation required.** "This is what we use for X" is an editorial judgement, not an observation |

Record absence as well as presence: `not found`, with the method and date, saves a re-probe in every session until
it expires; `declined` is a persistent answer and saves asking again.

An installed entry **must** reference a catalogue entry by id. If the tool is in neither catalogue, write the
custom entry first, otherwise the host layer degenerates into an undocumented list of paths.

## The machine file

`~/.mem/hosts/<hostname>/machine.md` — `%USERPROFILE%\.mem\hosts\<hostname>\machine.md` on Windows. It belongs
to the core: its location, identities, summary, observation rules and write protocol are in `MEM.md`, "Machine base",
and apply here unchanged. This extension's schema for its rows and sections is the installed entry in
`TOOL.template.md`. It is per OS account and per machine, and in no repository, so it never produces a merge conflict
and one machine's reality never overwrites another's.

The core creates the file before any tool is used, so that a path observed for the first time always has its
destination, rather than landing in a catalogue entry, `references/` or a daily log.

### The tools root

**Where do portable tools live on this machine?** Recorded as the `tools root` summary row, asked **once per
machine**, the first time it is needed.

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

Per-tool paths are written relative to the tools root, so a whole toolchain can be relocated by editing one row.
The machine file is never committed, so its paths may be absolute; it never records a credential. A tool needing
an auth token documents the variable **name**, never its value.

### Legacy host files

Two older places held machine facts. They are read, never written, by this version:

| Legacy file | Written by | Handling |
|---|---|---|
| `~/.mem/mem-toolbox/host.md` | `mem-toolbox` 1.0.3, possibly still running in other knowledge bases | The core merges its newer observations into the machine file — see `MEM.md`, "Machine base". It stays a live file until `mem-toolbox/1.1.0/legacy-retire` is applied |
| `custom/installed/<host>.md` in a knowledge base | `mem-toolbox` 1.0.0 – 1.0.2, and 1.0.3 with `extensions_mem_toolbox_kb_copy` | A reconciliation, below; removal by `mem-toolbox/1.1.0/remove-host-copy/<host>` |

**Importing a host copy** is a reconciliation, not a migration: whenever this knowledge base holds
`custom/installed/<hostname>.md` for **this** machine — matched by hostname, or by a label the user confirms once —
changed since its last import, merge it into the machine file: the tools root and `<runtime> env` lines as summary
rows when none exist yet, each tool section under the same-key rule (an older observation never replaces a newer one),
`outdated` read as `confirmed`, `unavailable` as `not found`, the old `source control` field dropped. No question is
asked again for anything it answers. A copy for **another** machine is never imported here: that machine imports it.
After an import, ask for an upgrade plan (see `MEM.md`, "Upgrade steps and ledgers"), so that the copy's
`remove-host-copy` instance is evaluated even when no version changed.

`extensions_mem_toolbox_kb_copy` is retired: a mirror of machine facts in a repository is precisely what goes stale and
misleads other machines. When it is still set, `mem-toolbox/1.1.0/drop-kb-copy` removes it; until then it is ignored.

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

A library whose runtime is missing or `not found` is not probed: report the runtime, not the library.

## Agent environments

The agent keeps **one environment per runtime, per machine** — never one per project — and records it in the machine
file as the `<runtime> env` summary row.

### The question, always asked

Which environment to use is the user's decision. The agent **must** ask it the first time a runtime is needed on
a host, **must not** preset or infer an answer, and **must** state the trade-offs every time it asks:

| | `dedicated` | `system` |
|---|---|---|
| Every project on this machine shares the same tools and versions | **yes** | **yes** |
| Isolated from the OS and from other software | yes | no — shared with every program using that interpreter |
| Needs admin rights | no | often |
| Undone by | deleting one folder | uninstalling package by package |
| The agent may install into it, with approval | yes | no — it proposes, the user runs |
| Survives an interpreter upgrade | the folder remains; rebuild it for a new `X.Y` | packages may be dropped with the old interpreter |
| Costs | one more directory, invoked through its own interpreter path | none to create; a Python marked *externally managed* ([PEP 668](https://peps.python.org/pep-0668/)) refuses `pip install` outright |

The first row is deliberately the same in both columns: sharing across projects comes from having **one
environment per machine**, not from choosing the system interpreter. What neither gives is the same versions on
**another** host — that is what `min version` in the entry is for.

The answer is recorded and not re-asked on that machine. Every install approval restates it in one line, so the
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

### Below a `min version`

An entry **may** declare a `min version`. Whether an observed version meets it is decided **at use**, against this
project's effective entry (custom over catalogue) — never stored in the machine file, because the same version can
satisfy one project and not another. Below it, the tool stays usable; the agent says once per session that it is
below this project's minimum, with a proposal at the level above. A refused update is recorded as
`update declined: <date>` in that section, and **must not** be proposed again until the user asks.

## Boundary with `references/` and with project dependencies

`references/` holds project facts: dependencies, canonical URLs, useful commands. This extension holds
**capability state**. If the question is *"may I run this, and how"*, it belongs here.

A library the **product** depends on — declared in `requirements.txt`, `pyproject.toml`, `package.json` — is a
project fact, not agent tooling. It belongs to the project's own manifest and to `references/`, and the agent
**must not** install it into an agent environment as a substitute for the project's own setup.
