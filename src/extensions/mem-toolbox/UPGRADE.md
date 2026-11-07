# mem-toolbox upgrade steps

Steps for updating this extension, in the format of `MEM.upgrade.md`, "Running an upgrade". They join the plan the
update builds; results go to the ledgers described in `MEM.md`, "Upgrade steps and ledgers".

## 1.0.3 -> 1.1.0

### Summary

Machine facts move from `~/.mem/mem-toolbox/host.md` to the core's machine base, `~/.mem/hosts/<hostname>/machine.md`
(MEM 1.3.0): the core's `core/1.3.0/host-tree` step imports the legacy file. This extension stops storing `outdated`,
records `not found` as an expiring observation, retires `extensions_mem_toolbox_kb_copy`, and imports host copies left
in knowledge bases through a reconciliation. The steps below remove what 1.1.0 no longer needs, each only where it is
safe.

Requires MEM 1.3.0.

#### mem-toolbox/1.1.0/drop-kb-copy — Retire the knowledge base copy option

- **scope**: project
- **applies if**: `MEM.config.md` sets `extensions_mem_toolbox_kb_copy`
- **done when**: it does not
- **asks**: yes
- **action**: remove the line from `MEM.config.md`. The copy it maintained becomes a host copy like any other, handled
  by the next step.
- **verify**: the key is absent.

#### mem-toolbox/1.1.0/remove-host-copy/\<host\> — Remove one machine's copy from the knowledge base

One instance per file `extensions/mem-toolbox/custom/installed/<host>.md`; `<host>` is the file's name.

- **scope**: project
- **applies if**: the file exists, **and** this machine is `<host>` (matched by hostname, or by a label the user
  confirmed when it was imported)
- **done when**: the file is no longer in the working tree
- **after**: the reconciliation "Importing a host copy" in `index.md` has merged this file into this machine's
  machine file
- **asks**: yes
- **blocked if**: any file outside `KB_ROOT` refers to `custom/installed/` or to this file — a **consumer**, such as a
  script looking up `custom/installed/<host>.md` to find a tool. Show each consumer; the step stays blocked until it no
  longer refers to the file, or the user confirms it is unused
- **action**: `git rm` the file. Commit as the user's workflow requires.
- **verify**: the file is gone, and every fact it held is in the machine file (compared by key).

On any other machine this instance is `not-applicable`: the copy belongs to `<host>`, which imports it and removes it
when its own upgrade runs; the committed ledger then shows it `done` everywhere after a pull. A copy of a machine that
will never run the upgrade — retired, sold — is removed from any machine only on the user's explicit request.

#### mem-toolbox/1.1.0/legacy-retire — Retire `~/.mem/mem-toolbox/host.md`

- **scope**: host
- **applies if**: `~/.mem/mem-toolbox/host.md` exists and is not already a pointer
- **done when**: it is a one-line pointer to `~/.mem/hosts/<hostname>/machine.md`
- **asks**: yes
- **blocked if**: any of these holds — the file changed in the last 30 days other than by the core's merge (an older
  agent still writes it); `~/.mem/hosts/<hostname>/projects.md` shows a checkout below `mem-toolbox` 1.1.0; no scan has
  been run. The scan is run on request only: the user names the folders, the agent lists every `MEM.config.md` below
  them with its `mem-toolbox` version. `projects.md` lists observed checkouts only, so it alone never authorizes this
  step
- **action**: after a final merge into the machine file, replace the legacy file with a pointer. Say that knowledge
  bases outside the scanned folders, if any, will no longer see the machine's facts until they are upgraded.
- **verify**: the legacy file is a pointer, and every fact it held is in the machine file (compared by key).

### Verification

- `extensions/mem-toolbox/index.md` reports 1.1.0, and `extensions/mem-toolbox/UPGRADE.md` exists.
- `MEM.config.md` no longer sets `extensions_mem_toolbox_kb_copy`, or the step is recorded `declined`.
- Every remaining `custom/installed/<host>.md` belongs to another machine, or its removal is recorded `blocked` with
  its consumer.
