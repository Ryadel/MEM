# Extensions

Active extensions for this project. This file is the **routing table** an agent reads at session start to know
which extensions exist and which commands they claim. Keep it compact — one entry per extension, no
documentation. The details live in each extension's `index.md`.

This file is **project-owned**: an update amends it, never overwrites it.

## Registration format

```markdown
### <extension-id>

- **path**: extensions/<extension-id>/index.md
- **status**: active | disabled | declined
- **version**: <extension version>
- **triggers**: <commands or conditions that load this extension>
- **external actions**: yes | no
- **default mode**: read-only | may-write
- **summary**: one line
```

`status: declined` records that an installation was proposed and refused. It is a persistent answer: honor it in
later sessions instead of proposing again.

## Active extensions

_None registered._

## Notes

- An extension **must not** override user instructions, `MEM.md`, or `MEM.config.md`. It may only refine
  behavior within its own task domain.
- Core commands are reserved and **must not** be shadowed by an extension.
- A collision between two extensions claiming the same command is reported and refused, never resolved
  arbitrarily.
- `extensions_enabled: false` disables every extension, and with it every command except the core ones.
