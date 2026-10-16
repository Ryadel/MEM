# Tool entry template

Two shapes: a **catalogue entry** describing a tool, and an **installed entry** describing what exists on one
host. They are separate because a catalogue entry is portable and an installed entry is not.

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

Written into the **machine file**, `~/.mem/mem-toolbox/host.md` (`%USERPROFILE%\.mem\mem-toolbox\host.md` on
Windows): one file per host, outside every repository, one section per tool. It is created by `MEM TOOLS SETUP` or
at first need with the header alone, before any tool has been probed. A header with no tool sections is a valid,
meaningful file — "this host is known, nothing probed yet". With `extensions_mem_toolbox_kb_copy: true` the same
content is mirrored into the knowledge base as `custom/installed/<host>.md`.

```markdown
# <host>

- **os**: <platform and version>
- **tools root**: <directory portable tools are unpacked into> | none
- **<runtime> env**: dedicated `<path>` | system — one line per runtime, written when first asked

## <tool>

- **status**: confirmed | outdated | unavailable | declined
- **path**: <relative to the tools root, or environment-relative when outside it>
- **version**: <observed version>
- **verified**: <date>, <how — for example the output of a version flag>
- **update declined**: <date> — only when an update of an `outdated` tool was refused
```

A library section has no `path`: it names the environment instead.

```markdown
## <library>

- **status**: confirmed | outdated | unavailable | declined
- **env**: <runtime> env
- **version**: <observed version>
- **verified**: <date>, <how — for example `importlib.metadata.version("<package>")`>
```

### Field rules

| Field | Rule |
|---|---|
| `tools root` | **Asked once per host, never guessed**, and recorded once at the top. Per-tool paths are written relative to it, so a whole toolchain can be relocated by editing one line. `none` is a valid answer and means every tool comes from a platform installer or a package manager |
| `<runtime> env` | **Asked, never preset**, the first time that runtime is needed on the host, with the trade-offs in `index.md`, "The question, always asked". Absent means "not yet asked" — never read it as `system` |
| `status` | `unavailable` and `declined` are persistent answers. Recording absence is what stops the agent re-probing and re-asking every session. `outdated` means present and working, below the entry's `min version` |
| `path` | Under the tools root, use `<tool-id>/<version>[-<variant>][-<target>]/…` — see "Where tools live on disk". Outside it, absolute paths are fine in the machine file; in a knowledge base copy prefer `%LOCALAPPDATA%`, `%PROGRAMFILES%`, `$HOME`: a full path leaks a username and internal layout into a committed repository |
| `version` | The **observed** version, from the tool answering, not the one read off a folder name. The two disagree more often than expected: a folder named `8.18` can hold `8.18.4` |
| `verified` | Availability observed on **another** host is a hint about what to try, never proof. Say so when relying on it |

An installed entry **must** name a tool that exists in `catalog/` or in `custom/tools/`. Write the catalogue
entry first if it does not.

A tool installed by a platform installer — under `Program Files`, a package manager, or a store — has no
version folder to point at and does not get one. Record its path as the installer left it and say so.

## Safety

An entry contains a command the agent will run, so it is stored instruction text: reviewed like any repository
file, unable to grant itself permissions the configuration denies, never carrying a secret, and never carrying
an install command. The agent never installs on its own; the one install it may run is the approved one in
`index.md`, "Installing", and its command lives in the approval, never in an entry.
