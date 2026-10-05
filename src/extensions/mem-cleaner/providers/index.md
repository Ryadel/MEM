# Providers: capability → provider

Keyed by **capability and role**, because a pipeline stage asks for what it needs, not for a name. Read this to
find a candidate, then read that provider's own page.

| Capability | Role | Candidates |
|---|---|---|
| `unicode` | `transform` | [watermarks-remover](watermarks-remover.md) |
| `statistical-rewrite` | `transform` | [watermarks-remover](watermarks-remover.md) — **local model required** |

One provider ships, with two operations of it. The remaining omissions are deliberate: `metadata-*` is left out
because upstream's behaviour depends on which optional system tools happen to be installed, which makes it
reproducible per host rather than deterministic. See the provider's own page.

`statistical-rewrite` was left out for a stated reason that turned out to be half wrong. Upstream ships no
rewrite *model* — true, and it never will, because it delegates to one you supply. But its `ollama` backend
addresses `127.0.0.1`, and upstream enforces a loopback allowlist that only `--allow-remote` lifts. A local
rewrite backend therefore exists, and reaching it crosses no network interface. The operation ships bound to
loopback, and the runner refuses any vector that says otherwise.

Project entries in `custom/providers/` are read as well, under their `custom/<id>` namespace. They **extend**
this table and never override it: a custom definition reusing a distributed id is refused.

## Capabilities

The vocabulary a stage may request. A provider declares which it implements and in which role.

| Capability | Meaning | Allowed in `safe` |
|---|---|---|
| `unicode` | Invisible or lookalike characters — joiners, bidi controls, non-ASCII spaces | Yes, region-scoped |
| `metadata-technical` | Generator strings, tool versions, build timestamps, editor artefacts — **allowlist required** | Yes |
| `metadata-attribution` | Author, copyright, licence, contact, identity fields | **No** |
| `c2pa` | Content Credentials assertions and manifests | **No** |
| `statistical-rewrite` | Rewriting text to alter its statistical signature | **No** — restricted; needs a named target, a local model and `tests` |
| `paraphrase` | Rewriting prose while preserving meaning | **No** — rewrite role |

A capability not in this list cannot be requested by a distributed pipeline. A project may define its own for a
custom provider and a custom pipeline; nothing distributed will reference it.

## Availability is not a path check

Being listed here says nothing about a provider being usable on this host, and the test differs by how the
provider ships:

| Ships as | "Available" means |
|---|---|
| A package in the runner's environment | The package **imports** there — not that a file exists somewhere |
| A standalone binary | The path exists and answers a version probe |

`custom/host/<host>.md` records the resolved interpreter or shim, because a machine with several environments
can satisfy "importable" in one and not another.

Where `mem-toolbox` is installed it can attest the executable — path, version, presence. It cannot attest models
being present, a driver working, an environment importing, or runner compatibility. Those are recorded here.

**Nothing is ever installed automatically.** A missing provider is reported with its upstream URL.

## Roles

| Role | Promise |
|---|---|
| `inspect` | Reads and reports. Changes nothing |
| `transform` | Produces a candidate file. Never writes over the original itself |
| `validate` | Returns a verdict on a candidate |

A provider declares only the roles it implements. `deterministic: true` means **reproducible**, never harmless.
