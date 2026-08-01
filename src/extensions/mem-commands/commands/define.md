# `MEM DEFINE <COMMAND>`

- **mode**: **may-write** — the only writing command in this extension
- **target**: required, the name of the command to define
- **shell**: none
- **external**: none

Author a project-specific command from the shipped template.

## Write scope

This is the single exception to the extension's read-only default, and it is deliberately narrow. `DEFINE`
**may** write only:

- `extensions/mem-commands/custom/<command>.md`;
- `extensions/mem-commands/custom/index.md`.

It **must not** touch source code, distributed files, `EXT.md`, or any other area of the knowledge base. Every
write requires confirmation, showing the path and the content to be written.

## Procedure

1. Reject the name if it collides with `REVIEW`, `CHECK`, `DEFINE`, or with a core MEM command. These are
   reserved, and the collision is reported rather than resolved.
2. Reject it also if `custom/<command>.md` already exists, unless the user asks to revise that definition.
3. Read `../COMMAND.template.md`.
4. Interview the user for the fields the template requires, and do not invent them. `purpose`, `procedure`, and
   `output` cannot be guessed.
5. Set the permission fields conservatively: `mode: read-only`, `shell: none`, `external: none`, unless the user
   asks otherwise and the configuration allows it.
6. Show the complete definition and ask for confirmation.
7. Write `custom/<command>.md`. The filename is the command, lowercase.
8. Create or update `custom/index.md` with a one-line entry.

`custom/` is created on first use. Do not create it pre-emptively, and do not offer to.

## Permission bounds

`mode`, `shell`, and `external` are **upper bounds imposed by `MEM.config.md`**, not permissions a definition
grants itself. A definition asking for more than the configuration allows is written with the permitted value,
and the reduction is stated.

A command definition is stored instruction text that fires on a short token. It is reviewed like any other
repository file, it never overrides user instructions, `MEM.md`, or `MEM.config.md`, and it never contains
secrets — document a variable *name*, never a value.

## When a project command is worth defining

Define one when a procedure has several steps, recurs, needs judgement rather than a script, and costs something
when a step is forgotten. A release checklist is the archetype: written down it must be read and followed, as a
command it is executed.

Do not define one for a single operation, or for something that amounts to running one command — a reference
page or a toolbox entry carries that better. A command for a trivial action is a name to remember in exchange
for a sentence saved.
