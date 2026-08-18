# Provider definition template

A provider declares what it can do. The pipeline engine never knows what it *is* — it resolves ids through a
generic registry and contains no provider id of its own.

Two shapes: an **adapter provider**, backed by code in the runner, and a **CLI provider**, defined entirely by a
project. Both use the same front matter, which is why a project-authored provider is not second-class.

Front matter is used here because the runner parses this file as well as the agent. That is the whole licence
for it: **front matter belongs where a non-agent program parses the file**, and the body below keeps MEM's
ordinary prose style.

## Adapter provider

Copy into `providers/<id>.md`. The filename is the id.

```markdown
---
schema: provider/1
id: <id>
version: <provider definition version>
license: <SPDX identifier>
locality: local | remote | optional-remote

operations:
  <operation-id>:
    role: inspect | transform | validate
    capability: <capability key>
    deterministic: true | false
    chainable: true | false
    regions: prose | runtime | any
    allowlist:
      - <field or class, when the capability requires one>
---

# <id>

What it is, who publishes it, and when to prefer it.

## Requirements

What must exist for it to run: a package, a driver, a model, an environment.

## Notes

Flags that matter, constraints already paid for.
```

## CLI provider

Copy into `custom/providers/<id>.md`. The id is namespaced `custom/<id>` and **may not** shadow a distributed
one; a collision is refused, not resolved.

```markdown
---
schema: provider/1
id: custom/<id>
version: 1
type: cli
locality: local

command: <executable>
args:
  - <argument>
  - "${input}"
  - "--output"
  - "${output}"

operations:
  <operation-id>:
    role: transform
    capability: <capability key>
    deterministic: true
    chainable: true
    regions: prose
---

# custom/<id>

What it does and why this project uses it.
```

Variables: `${input}`, `${output}`, `${workspace}`, `${language}`, `${agent}`, `${pipeline}`.

## Field rules

| Field | Rule |
|---|---|
| `id` | The filename. Custom ids are namespaced `custom/<id>`; shadowing a distributed id is refused |
| `role` | `inspect` reads, `transform` rewrites, `validate` judges. The validator counts roles — a capability alone does not say whether a stage modifies anything |
| `capability` | What the operation achieves, so a pipeline can request it without naming a provider |
| `deterministic` | Means **reproducible**, never harmless. Do not read it as a safety claim |
| `chainable` | Whether the operation may be followed by another in the same run. Rewrite operations are `false` |
| `regions` | Which classified regions the operation may touch. `prose` never includes directives or docstrings |
| `allowlist` | Required for any capability whose scope would otherwise be open-ended, `metadata-technical` above all. An allowlist is enumerated; a wildcard is refused |
| `locality` | `remote` and `optional-remote` are refused at 1.0: no provider sends file content off the machine |
| `command` / `args` | An **argv vector**. No shell string. Each variable substitutes as one argument, never expanded into the command line |
| `license` | Read from upstream and dated. A wrong licence in a distributed catalogue is worse than a blank one |

## Roles are obligations, not labels

A project that only detects should be able to say so. `inspect` promises to read and report; `transform`
promises to produce a candidate; `validate` promises a verdict on one. A provider declares only the roles it
actually implements, and the engine never assumes a fourth.

## Approval binds the implementation

For a CLI provider, approval is not of this file — it is of what this file will execute:

| Declared artifact | Bound by |
|---|---|
| A repository-relative script or directory | Content hash of the file, or of the tree |
| A binary outside the repository | Resolved absolute path, reported version, **and the executable's content hash** |
| An interpreter whose dependency closure cannot be determined | **Not bindable** — confirmation on every run, never eligible for `automatic` |

A changed bound value lapses the approval.

## Safety

A definition contains a command the runner will execute, so it is **stored instruction text**: reviewed like any
repository file, unable to grant itself permissions the configuration denies, never carrying a secret, and never
carrying an install command. The agent never installs a provider.
