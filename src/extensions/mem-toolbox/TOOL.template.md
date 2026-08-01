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

Written into `custom/installed/<host>.md`, one file per host, one section per tool.

```markdown
# <host>

- **os**: <platform and version>

## <tool>

- **status**: confirmed | unavailable | declined
- **path**: <full or environment-relative path>
- **version**: <observed version>
- **verified**: <date>, <how — for example the output of a version flag>
```

### Field rules

| Field | Rule |
|---|---|
| `status` | `unavailable` and `declined` are persistent answers. Recording absence is what stops the agent re-probing and re-asking every session |
| `path` | Prefer `%LOCALAPPDATA%`, `%PROGRAMFILES%`, `$HOME`. A full path leaks a username and internal layout into a committed repository |
| `verified` | Availability observed on **another** host is a hint about what to try, never proof. Say so when relying on it |

An installed entry **must** name a tool that exists in `catalog/` or in `custom/tools/`. Write the catalogue
entry first if it does not.

## Safety

An entry contains a command the agent will run, so it is stored instruction text: reviewed like any repository
file, unable to grant itself permissions the configuration denies, never carrying a secret, and never carrying
an install command. The agent never installs a tool on its own.
