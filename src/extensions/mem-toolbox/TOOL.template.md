# Tool entry template

Two shapes: a **catalogue entry** describing a tool, and an **installed entry** describing what exists on one
host. They are separate because a catalogue entry is portable and an installed entry is not.

## Catalogue entry

Copy into `custom/tools/<tool>.md`. The filename is the tool id.

```markdown
# <tool>

- **kind**: cli | library | service
- **capability**: <one or more task keys, matching the index>
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
| `kind` | Not cosmetic. A library is not found with `which`, and its licence implications differ: invoking a GPL binary does not affect your project's licensing, linking a library can |
| `capability` | The lookup key. Indexes are keyed by capability, not by tool name, because the question is "resize an image", not "imagemagick" |
| `licence` | Read from upstream before writing it, and record the date. A wrong licence in a shared catalogue is worse than a blank one |
| `url` | The upstream project page. **Never an install command**: a list of download URLs must not become an installer |
| `invocation` | The command form, never a credential. Document a variable *name* |

## Installed entry

Written into `custom/installed/<host>.md`, one file per host, one section per tool. This file is the
extension's **bootstrap entry**: it is created at installation with the header alone, before any tool has been
probed. A header with no tool sections is a valid, meaningful file — "this host is known, nothing probed yet".

```markdown
# <host>

- **os**: <platform and version>
- **tools root**: <directory portable tools are unpacked into, environment-relative where possible>
- **source control**: yes | no

## <tool>

- **status**: confirmed | unavailable | declined
- **path**: <relative to the tools root, or environment-relative when outside it>
- **version**: <observed version>
- **verified**: <date>, <how — for example the output of a version flag>
```

### Field rules

| Field | Rule |
|---|---|
| `tools root` | **Asked at installation, never guessed**, and recorded once at the top. Per-tool paths are written relative to it, so a whole toolchain can be relocated by editing one line. `none` is a valid answer and means every tool comes from a platform installer or a package manager |
| `source control` | The answer given once at installation, default `yes`. Recorded so a later session does not re-ask, and so `no` is visibly a decision rather than an oversight |
| `status` | `unavailable` and `declined` are persistent answers. Recording absence is what stops the agent re-probing and re-asking every session |
| `path` | Under the tools root, use `<tool-id>/<version>[-<variant>][-<target>]/…` — see "Where tools live on disk". Outside it, prefer `%LOCALAPPDATA%`, `%PROGRAMFILES%`, `$HOME`: a full path leaks a username and internal layout into a committed repository |
| `version` | The **observed** version, from the tool answering, not the one read off a folder name. The two disagree more often than expected: a folder named `8.18` can hold `8.18.4` |
| `verified` | Availability observed on **another** host is a hint about what to try, never proof. Say so when relying on it |

An installed entry **must** name a tool that exists in `catalog/` or in `custom/tools/`. Write the catalogue
entry first if it does not.

A tool installed by a platform installer — under `Program Files`, a package manager, or a store — has no
version folder to point at and does not get one. Record its path as the installer left it and say so.

## Safety

An entry contains a command the agent will run, so it is stored instruction text: reviewed like any repository
file, unable to grant itself permissions the configuration denies, never carrying a secret, and never carrying
an install command. The agent never installs a tool on its own.
