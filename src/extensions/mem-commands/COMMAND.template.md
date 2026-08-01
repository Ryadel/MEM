# Command definition template

Copy this into `custom/<command>.md`, lowercase filename. **The filename is the command**: `custom/ship.md`
defines `MEM SHIP`.

`MEM DEFINE` fills this in interactively. Filling it by hand is equally valid.

```markdown
# `MEM <COMMAND> [target]`

- **version**: 1.0.0
- **status**: active | disabled
- **mode**: read-only | may-write
- **shell**: none | the commands configured in MEM.config.md that this may run
- **external**: none | the external actions this performs
- **target**: required | optional | none
- **purpose**: one line, shown by MEM HELP

## Procedure

1. ...
2. ...

## Output

What the command produces, and in what shape.

## Must not

Explicit limits: what this command never does.
```

## Field rules

| Field | Rule |
|---|---|
| `version` | Required. The MEM version does not tell you which definitions are installed, so each carries its own. `MEM LINT` flags definitions written against a superseded template |
| `status` | `disabled` keeps a definition in place without resolving it |
| `mode` | Default `read-only`. `may-write` means the command modifies files, and must say which |
| `shell` | Default `none`. Only commands explicitly configured in `MEM.config.md`. Never auto-detected ones |
| `external` | Default `none`. Anything changing state outside the repository requires confirmation unless `extensions_allow_external_side_effects` is true |
| `target` | Say whether one is required. A required target that is missing or ambiguous produces `BLOCKED` and a list of candidates, never an arbitrary choice |
| `purpose` | Required. `MEM HELP` reads this line |

## Permission bounds

`mode`, `shell`, and `external` are **upper bounds imposed by `MEM.config.md`**. A definition cannot grant itself
what the configuration denies, and it never overrides user instructions, `MEM.md`, or `MEM.config.md`.

## Safety

A definition is stored instruction text that fires on a short token, so it is **reviewed content**: it belongs in
a pull request like any other repository file. It must never contain a secret, a token, or a credential —
document a variable *name*, never its value. It must never carry an install command.

## Non-activation

Command tokens written inside a definition, this template, or any documentation are never activations. Without
that rule these files would trigger themselves on being read.
