# Tool entry template

Two shapes: a **catalogue entry** describing a tool, and an **installed entry** describing what exists on one
machine. They are separate because a catalogue entry is portable and an installed entry is not.

## Catalogue entry

Copy into `custom/tools/<tool>.md`. The filename is the tool id.

```markdown
# <tool>

- **kind**: cli | library | runtime | service
- **capability**: <one or more task keys, matching the index>
- **requires**: <runtime id> — libraries only
- **package**: <registry name> — libraries only
- **import**: <import name> — libraries only, when it differs from `package`
- **min version**: <oldest acceptable version, and why> — optional
- **purpose**: what it is used for here, and when to prefer it over the alternatives
- **invocation**: the canonical command form
- **licence**: <SPDX identifier where one exists>, verified <date>
- **url**: <upstream project page>

## Notes

Flags that matter, version constraints, gotchas already paid for.

## Alternatives

Related tools, and why this one is preferred.
```

### Field rules

| Field | Rule |
|---|---|
| `kind` | Not cosmetic. A library is not found with `which`, and its licence implications differ: invoking a GPL binary does not affect your project's licensing, linking a library can. A `runtime` is what libraries `requires`; it is probed like a CLI tool, owns an agent environment, and is what `MEM TOOLS CHECK` probes |
| `requires` | A runtime id from a catalogue. A library without it cannot be probed |
| `package` | The name an install takes, and the **only** name an approval may install — see "Installing" in `index.md`. Copy it from the registry page, never retype it |
| `import` | Omit only when identical to `package`. `Pillow` imports as `PIL`; guessing the import from the package is how a probe reports a present library as missing |
| `min version` | Decided offline from the upstream support policy, with its source. Never "latest": that changes daily and needs the network to check |
| `capability` | The lookup key. Indexes are keyed by capability, not by tool name, because the question is "resize an image", not "imagemagick" |
| `licence` | Read from upstream before writing it, and record the date. A wrong licence in a shared catalogue is worse than a blank one |
| `url` | The upstream project page. **Never an install command**: a list of download URLs must not become an installer |
| `invocation` | The command form, never a credential. Document a variable *name* |

## Installed entry

Written into the **machine file** of the core's machine base, `~/.mem/hosts/<hostname>/machine.md`
(`%USERPROFILE%\.mem\hosts\<hostname>\machine.md` on Windows): one file per machine and OS account, outside every
repository, shared by every project — see `MEM.md`, "Machine base". The core creates it with its **summary** table;
this extension adds rows to that table and one section per tool. Every write uses the script in `MEM.md`, "Writing
shared files": a summary row with mode `row`, a tool section with mode `section`.

Summary rows this extension owns:

```markdown
| tools root | <directory portable tools are unpacked into> \| none |
| <runtime> env | dedicated `<path>` \| system — one row per runtime, written when first asked |
```

A tool section:

```markdown
## <tool>

- **status**: confirmed | not found | declined
- **path**: <relative to the tools root, or absolute when outside it>
- **version**: <observed version>
- **verified**: <ISO date>, <how — for example the output of a version flag>
- **update declined**: <date> — only when a proposed update was refused
```

A library section has no `path`: it names the environment instead.

```markdown
## <library>

- **status**: confirmed | not found | declined
- **env**: <runtime> env
- **version**: <observed version>
- **verified**: <ISO date>, <how — for example `importlib.metadata.version("<package>")`>
```

### Field rules

| Field | Rule |
|---|---|
| `tools root` | **Asked once per machine, never guessed**. Per-tool paths are written relative to it, so a whole toolchain can be relocated by editing one row. `none` is a valid answer and means every tool comes from a platform installer or a package manager |
| `<runtime> env` | **Asked, never preset**, the first time that runtime is needed on the machine, with the trade-offs in `index.md`, "The question, always asked". Absent means "not yet asked" — never read it as `system` |
| `status` | An **observation** (`confirmed`, `not found`) or a **refusal** (`declined`). `not found` records the method and date, never proves absence, and expires after 30 days; before telling the user a tool is missing, probe once more. `declined` persists until the user changes it. There is no `outdated` status: whether a version satisfies a `min version` is decided at use, for the project at hand. Legacy files may say `unavailable` (read it as `not found`) or `outdated` (read it as `confirmed`) |
| `path` | Under the tools root, use `<tool-id>/<version>[-<variant>][-<target>]/…` — see "Where tools live on disk". Outside it, absolute paths are fine: the machine file is in no repository |
| `version` | The **observed** version, from the tool answering, not the one read off a folder name. The two disagree more often than expected: a folder named `8.18` can hold `8.18.4` |
| `verified` | An ISO date first, so that two observations of the same key compare: the script never replaces a section with an older one. Availability observed on **another** machine is a hint, never proof |

An installed entry **must** name a tool that exists in `catalog/` or in `custom/tools/`. Write the catalogue
entry first if it does not.

A tool installed by a platform installer — under `Program Files`, a package manager, or a store — has no
version folder to point at and does not get one. Record its path as the installer left it and say so.

## Safety

An entry contains a command the agent will run, so it is stored instruction text: reviewed like any repository
file, unable to grant itself permissions the configuration denies, never carrying a secret, and never carrying
an install command. The agent never installs on its own; the one install it may run is the approved one in
`index.md`, "Installing", and its command lives in the approval, never in an entry.
