# Extension: `mem-cleaner`

- **version**: 0.1.0
- **provides**: `CLEAN`, and configurable post-processing pipelines
- **subcommands**: `SAFE`, `FULL`, `TEST`, `STATUS`, `PROVIDERS`, `PIPELINES` — closed set
- **precedence**: **base wins** — a custom definition may not shadow a distributed id
- **external actions**: no
- **executable content**: **yes** — `runner/*.py`, see below
- **default mode**: may-write
- **bootstrap entry**: `custom/host/<host>.md`
- **schema version**: `provider/1`, `pipeline/1`
- **requires**: Python 3.8 or newer on the host. Nothing else

Post-processes files an agent has just written, through pipelines whose every transformation lives behind a
provider.

> **0.1.0 cleans.** One provider ships — `watermarks-remover`, Layer A — and the `safe` profile runs it over
> prose regions only, transactionally, validated, with rollback. `FULL` has nothing to do yet: no rewrite
> provider exists, and 1.0 ships none.

## Extraction: how a provider that is not region-aware stays in its lane

The shipped provider cleans a byte stream. Handed a whole source file it strips invisible characters from
string literals as readily as from comments — measured, not assumed.

So it is never handed a whole file:

```text
classify --> extract only the permitted regions --> provider --> splice back
```

Everything outside those regions is **copied verbatim from the original**, so out-of-scope bytes cannot change
even in principle. The regions travel as one payload joined by a sentinel, so one invocation cleans a whole
file; if the sentinel does not come back intact the result is refused rather than guessed at.

Two checks, for two shapes of result:

| Situation | Check |
|---|---|
| A spliced result | Every byte outside the spans is compared against the original — **exact** |
| A provider handed the whole file (`regions: any`) | `verify()` attributes changed bytes to regions — deliberately over-reports |

The exact check exists because the approximate one is wrong here: `verify()` bounds a change by common prefix
and suffix, so two edits far apart read as one span covering the untouched code between them. Safe as a sole
guard; wrong against a result that was *built* in scope.

## This extension ships code

`runner/` contains a small Python program, and it is **executable content** in the sense `MEM.md` defines:
installing this extension writes code into your repository, and updating it replaces that code. That requires
`extensions_allow_executable_content: true` — off by default — and an approval that names those files as
executable, separately from the Markdown.

MEM does not claim to constrain what that code does, because it cannot. What it offers instead is that the code
is **in your repository**, so an update arrives as a diff you can read in a pull request. That is only worth
anything while the runner stays small enough to actually read, which is a constraint on this extension rather
than on you.

Three properties keep it honest, and each is checkable:

| Property | Why | How to check |
|---|---|---|
| Standard library only | Nothing can install dependencies into your repository | `grep -r "^import\|^from" runner/` |
| Providers run as subprocesses, never imported | Keeps "which environment" a provider question, not a runner one | No `importlib`, no `__import__` |
| The engine holds no provider id | A new provider is a definition file, never an engine change | `grep -ri "<provider name>" runner/` finds nothing |

Add `__pycache__/` to your repository's ignore rules: the runner generates bytecode where it runs.

### Invoking it

There is no `mem-cleaner` on `PATH`. It is run as source, from where the extension was installed:

```text
<interpreter> <KB_ROOT>/extensions/mem-cleaner/runner/cli.py status
<interpreter> <KB_ROOT>/extensions/mem-cleaner/runner/cli.py providers
<interpreter> <KB_ROOT>/extensions/mem-cleaner/runner/cli.py pipelines
<interpreter> <KB_ROOT>/extensions/mem-cleaner/runner/cli.py validate-pipeline safe
<interpreter> <KB_ROOT>/extensions/mem-cleaner/runner/cli.py recover
<interpreter> <KB_ROOT>/extensions/mem-cleaner/runner/cli.py classify <file> [--show]
<interpreter> <KB_ROOT>/extensions/mem-cleaner/runner/cli.py record --session <id> <file>...
<interpreter> <KB_ROOT>/extensions/mem-cleaner/runner/cli.py recorded --session <id>
<interpreter> <KB_ROOT>/extensions/mem-cleaner/runner/cli.py approve [--mode automatic] [--revoke]
<interpreter> <KB_ROOT>/extensions/mem-cleaner/runner/cli.py run [--automatic] [--session <id>] [<file>...]
<interpreter> <KB_ROOT>/extensions/mem-cleaner/runner/cli.py test [<file>...]
```

**The working directory does not matter.** The runner lives inside the knowledge base it serves, so it locates
`KB_ROOT` from its own path first and only then from the current directory. Naming it by path is therefore
enough, from anywhere. `--kb-root` overrides both, for the case of one runner inspecting a different base.

The interpreter is resolved once and recorded in `custom/host/<host>.md`. `MEM CLEAN STATUS` reports it, along
with the runner version and the Python version — on a machine with several installations, a probe run against
the wrong one describes a state that is true of nobody.

The absence of a runner is no longer an ordinary state, since it ships with the extension. The equivalent state
is **no usable Python on this host**, which is reported and stops the command.

## The rule this extension is built around

**`mem-cleaner` does not know how to remove anything.** It knows capabilities, roles, pipeline rules, file
scope, execution policy and validation policy. Every technique lives behind a provider, and the pipeline engine
contains no provider id.

Consequence for anyone extending it: a new provider is a definition file, never a change to the engine.

## How this differs from `mem-toolbox`

They look alike and are not. `mem-toolbox` is a **registry** — it answers "which tool, and is it here" and
modifies nothing. `mem-cleaner` is an **orchestrator**: it runs things and replaces files, and in `automatic`
mode it does so at the end of a session without a command being typed.

Every safety rule below exists because of those two properties — autonomy and writing — not because a
subprocess is involved. Invoking a local process is not an external action.

## Layers

| Layer | Path | Distributed | Project-owned |
|---|---|---|---|
| Base | `providers/`, `pipelines/`, the templates | Yes, via the manifest | No |
| Custom | `custom/providers/`, `custom/pipelines/` | Never | Yes |
| Host | `custom/host/<host>.md` | Never | Yes, per machine |

```text
extensions/mem-cleaner/
  index.md                  this file
  PROVIDER.template.md      provider definition schema
  PIPELINE.template.md      pipeline definition schema
  commands/
    clean.md                the MEM CLEAN command
  providers/
    index.md                capability -> provider
  pipelines/
    index.md                available pipelines
  custom/                   never distributed, never in the manifest
    providers/<id>.md
    pipelines/<id>.md
    host/<host>.md          bootstrap entry
```

### Precedence: base wins, and collisions are refused

This is the **opposite** of `mem-toolbox`, deliberately. There, a custom entry overrides reference data — a
claim about which tool is better — and being closer to the truth about this project, it should win. Here a
definition names a command that will be executed, possibly unattended, over files just written.

So:

- a custom definition **must not** reuse the id of a distributed provider or pipeline. A collision is
  **refused**, never resolved;
- custom ids are namespaced `custom/<id>`, so a pipeline stage naming one says so on its face;
- an override never happens silently, because an override never happens.

Do not harmonise this with `mem-toolbox`. Each extension declares its own direction and each says why.

## Configuration

All options are project facts and live in `MEM.config.md`. Defaults:

```yaml
extensions_cleaner_enabled: true
extensions_cleaner_mode: "manual"
extensions_cleaner_pipeline: "safe"
extensions_cleaner_max_rewrite_stages: 1
extensions_cleaner_validation: "syntax"
extensions_cleaner_fail_policy: "restore"
extensions_cleaner_include: []
extensions_cleaner_exclude: []
extensions_cleaner_update_daily_log: false

extensions_cleaner_format_command: null
extensions_cleaner_project_root: ".."
extensions_cleaner_validation_timeout: 600
```

`extensions_cleaner_project_root` is where validation commands run, relative to `KB_ROOT`. The default `..` is
right for the common `<project>/MEM/` layout and wrong for anything else, so `MEM CLEAN STATUS` prints the
resolved path rather than leaving it assumed.

This extension also **reads** `build_command` and `test_command` from the core configuration. It never writes
them, and it never invents one: `auto-detect`, `none` and an empty value all mean *there is no such command*.

`extensions_cleaner_mode` is **not** defaulted in practice: it is answered at installation, and a missing or
unreadable value means `manual`. A missing key is never consent — and neither is an unreadable one, which is
reported rather than quietly replaced by a default.

### The accepted configuration subset

The runner ships without dependencies, so it parses these files itself and accepts a **restricted subset**:
scalars, `true`/`false`/`null`, integers, quoted strings, nested mappings by indentation, lists of scalars, lists
of mappings, and the empty forms `[]` and `{}`. Block scalars, anchors, aliases, tags and non-empty flow
collections are **refused, not guessed** — a mis-parsed pipeline is a mis-executed one.

`MEM.config.md` is shared with the core and with other extensions, so a key belonging to someone else may fall
outside that subset. When that happens the runner recovers its own `extensions_cleaner_*` keys line by line and
**reports what it could not read**. It never treats an unreadable configuration as an absent one.

Options are prefixed `extensions_cleaner_` per `MEM.md`, "Registration". An unprefixed `cleaner_*` key is not
read.

## Autonomy: one question, asked at installation

| Mode | Behaviour |
|---|---|
| `automatic` | At the end of a session, the configured pipeline runs over the files this agent changed |
| `confirm` | Identical, but asks yes/no each time |
| `manual` | Nothing runs on its own. Only an explicit `MEM CLEAN` |

The agent **must** ask this at installation and record the answer. **The answer is the approval**, which is why
no default is proposed — a default would be an approval nobody gave.

### What the approval covers, and when it lapses

Approving *"clean my prose with this provider after the tests pass"* is not approving whatever the pipeline is
changed into tomorrow. So the approval records a **fingerprint** of what was approved, and lapses when any of
it changes:

- the pipeline and its stages, including each stage's region scope;
- the provider each stage resolved to, and its version;
- `extensions_cleaner_max_rewrite_stages`;
- the validation level.

A lapsed approval degrades to `manual` -- the mode that does nothing -- rather than to a prompt, because the
agent that would see the prompt is the one whose output is being cleaned.

```text
... cli.py approve                          show the current state
... cli.py approve --mode automatic --note "why"
... cli.py approve --revoke
```

An unattended run is invoked with `--automatic` and is refused unless the mode is `automatic` **and** the
fingerprint still matches. `confirm` and `manual` refuse it outright, each saying what to do instead.

`automatic` proceeds without prompting even when `extensions_require_confirmation: true`, because that option
governs *unapproved* operations and this one carries a recorded, named approval. `extensions_enabled: false`
disables everything, including `MEM CLEAN`.

### After a run, the record is re-baselined

The attribution record holds the hash the agent left behind, and cleaning changes it. Without correcting that,
the next run would skip the file as *changed since recorded* -- attributing this extension's own write to a
person, and never cleaning that file again.

So a successful commit re-records the files it changed. They stay attributed to the agent, which is still true:
the agent wrote them, and this only tidied what it was allowed to touch.

### "End of session"

Nothing fires in a Markdown model, so the obligation is placed at a moment the agent already recognises:
**before reporting the work complete.** The core's end-of-session checklist reaches the same moment but only
says "consider updating" — this extension states its own obligation rather than borrowing authority the
checklist does not grant.

There is no queue and no pending list. Per-write cleaning does not exist: rewriting a file while the agent is
still working on it invalidates the context it just read.

## Which files are eligible

Only files **this agent changed in this session**, identified from the attribution record:

- each entry is `path` + `expected_hash`, captured immediately after the agent's last write to that file;
- the record is namespaced by session id, so two agents on one host never share a set;
- it lives in per-host transient storage, never in the committed knowledge base, and holds paths and hashes
  only — never content;
- a file whose current hash differs from `expected_hash` is **skipped**: a human edited it, and a human's edit
  is not the agent's output to clean.

**Never derive this set from `git diff`.** It reports everything uncommitted, including work the user did before
the session began. Attribution comes from the operation that changed the file, never from style, heuristics or
working-tree state.

`MEM CLEAN <target>` may target anything explicitly. That is a user instruction, not an attribution claim.

### Keeping the record

The agent records each file **after its last write to that file**, and re-recording simply moves the baseline —
the agent wrote it again, so the new content is what must not change afterwards.

```text
... cli.py record --session <id> src/a.py src/b.py
... cli.py recorded --session <id>
... cli.py forget --session <id>
```

`recorded` shows what is eligible and, for everything else, **why**:

```text
Session sess-A: 4 recorded, 1 eligible

  src/a.py
  node_modules/d.py     SKIPPED: excluded by configuration
  src/b.py              SKIPPED: changed since recorded
  src/c.txt             SKIPPED: not matched by extensions_cleaner_include
```

Every exclusion is reported, because a file silently dropped from an automatic run is indistinguishable from
one that was cleaned successfully.

`extensions_cleaner_include` and `extensions_cleaner_exclude` are matched against the path relative to
`extensions_cleaner_project_root`. Patterns are `fnmatch`, whose `*` already crosses directory separators; a
leading `**/` is additionally tried stripped, so `**/*.py` also matches a top-level `b.py`. That accommodation
is stated rather than papered over.

## Pipelines

A pipeline is an ordered list of stages. Each stage declares a **role** and a **capability**; the provider is
resolved from configuration unless explicitly pinned.

```yaml
stages:
  - role: transform
    capability: unicode
  - role: validate
    builtin: syntax
```

`role` is `inspect | transform | validate`. It is what the validator counts, because a capability alone does not
say whether a stage reads or rewrites.

### Execution order and the rewrite limit

```text
inspect → transform … → rewrite (at most one) → format → validate
```

A pipeline with more rewrite stages than `extensions_cleaner_max_rewrite_stages` is **invalid** and refused
before anything runs. Raising the limit is allowed and warned about.

### `safe` is a profile name, not a guarantee

`safe` means *deterministic, allowlisted, region-scoped and validated*. That describes the process, not the
result. **`deterministic` means reproducible, never harmless**: stripping invisible Unicode can change behaviour
through a string literal, a regex, a fixture or a snapshot, all of which survive a successful parse.

## Regions: prose, directives, runtime

A transformation is applied to classified regions, never to a whole byte stream.

| Region | Examples | Treatment |
|---|---|---|
| **Prose** | Narrative comments, human documentation | Parse-level validation is proportionate |
| **Directives** | `# type: ignore`, `# pragma`, `# noqa`, `eslint-disable`, `// @ts-ignore`, `//go:build`, annotation processors | **Never touched.** A byte change alters compilation, linting or generation while the file still parses |
| **Runtime** | Docstrings — reachable as `__doc__`, executed by doctest — literals, regexes, fixtures, golden files, snapshots | Escalate to full validation, or leave alone |

**Doubt escalates.** An unclassifiable region is treated as runtime, never as prose. A classifier that cannot
tell a pragma from a sentence must escalate rather than guess. "Comments and docstrings are safe" is false.

Region boundaries are **byte offsets**, and the conversion from the tokeniser's character positions happens in
one place. The two units drift apart on any file containing a non-ASCII character, and a byte change outside a
comment can then land, in character space, inside one — accepting a forbidden edit as prose. Mixing the units
is a security bug, not a rounding error.

### Which files can be classified

| Type | Classifier | Prose is |
|---|---|---|
| `.py` | Python tokeniser | Narrative `#` comments only |
| `.md`, `.markdown`, `.txt` | Markdown | Text outside fenced blocks, inline code and indented blocks |
| anything else | **none** | nothing |

**No classifier means no touchable region — not "all prose".** A scoped stage refuses such a file rather than
guessing at it, and that refusal is reported. Widening this list is how 1.0 grows after release; treating an
unclassified file as prose would be how it breaks something.

Two accommodations, stated rather than hidden. A Python comment whose body looks like `word:` is treated as a
**directive even when the tool is unknown** — an unrecognised `# frobnicate: off` is far more likely a pragma
than a sentence, and being wrong that way only means "do not touch". And a Markdown line indented four spaces
is treated as runtime, because telling an indented code block from a list continuation needs a real Markdown
parser.

### The scope is checked, not trusted

After a stage runs, its output is compared against the original and **every changed byte is attributed to a
region**. A change reaching a kind the stage's scope does not permit is a violation, and the candidate is
rejected:

```text
byte 8 is directive, which a 'prose'-scoped stage may not change
```

The comparison is deliberately crude — the common prefix and suffix bound the change, and everything between
counts as touched. A precise diff would report less, and reporting less is the direction that lets a violation
through.

One subtlety worth knowing: a pure **insertion** sits between two bytes, and is attributed to the byte it was
appended to rather than the one that follows. Text added at the end of a comment is an edit to that comment,
even though the next byte is the newline outside it.

Inspect any file before trusting a pipeline on it:

```text
... cli.py classify src/a.py --show
```

## Validation

| Level | Adds | Needs |
|---|---|---|
| `syntax` | The minimum checks above. Always run | nothing |
| `format` | The project's formatter agrees with the result | `extensions_cleaner_format_command` |
| `project` | The project still builds | `build_command` |
| `tests` | The tests still pass | `test_command` |

**A level requires only the command it is named after.** Formatter, build and tests are independent guarantees,
not a ladder of the same one: a project with tests and no formatter can legitimately ask for `tests`. Lower
checks run when configured, and are reported as **not configured; unchecked** when not — which is not a silent
downgrade, because it is reported. "Not configured" and "passed" must never look alike.

Minimum validation is unconditional. A stronger level is required when a pipeline contains a rewrite stage, or
when the diff touches a runtime region — and the level applied is the **stronger** of what configuration asks
for and what the diff demands.

### Commands run without a shell

A configured command is split into an argument vector and executed directly. A command containing `|`, `&&`,
`>`, `;` or similar is **refused**, not run: without a shell those become extra arguments, the command does
something other than what was written, and very likely exits zero. A false pass is worse than a refusal. Put
such a command in a script the project owns and configure that — a file is reviewable in a way a configuration
string is not.

Commands run in `extensions_cleaner_project_root` and are killed after
`extensions_cleaner_validation_timeout` seconds.

**Cleaning runs after a green test suite**, and the post-clean run is the pipeline's own validation stage — not
an extra phase. A green baseline is what makes a later failure unambiguously the cleaner's.

**An escalation that cannot be satisfied is a refusal, not a downgrade.** Where no test command is configured,
`automatic` skips the transformation and reports it; an explicit `MEM CLEAN` states the reduced guarantee —
parse and formatter only — and asks. Silently accepting a weaker check is how a guarantee stops meaning
anything.

## Transactions

No file is modified in place. Every run is journalled:

```text
prepared ──► installed ──► validating ──► committed
                               │
                               └──► rolling-back ──► restored
```

- **`prepared`** records original hashes and backup locations before anything is touched.
- **The intention to install is durable before the file changes.** Each entry records its candidate hash and an
  `intended` flag, and that reaches disk *before* the replace; the confirmation follows it. A crash in that
  window leaves a journal saying "not installed" over a file that was — so recovery consults the file itself,
  and the candidate hash tells it what happened. Without this the backup would be discarded and the rollback
  lost, which is the worst outcome the design has.
- **An indeterminate file is never touched.** If an interrupted entry matches neither the original nor the
  candidate, someone has been in it since: recovery stops, reports, and keeps the journal.
- **`committed`** is written only after post-clean validation passes. Only then are backups discarded — clearing
  the journal once files are in place would discard rollback exactly when it becomes likely.
- Every replace is a **compare-and-swap** on the original hash, so a concurrent editor or a rebase aborts the
  swap instead of being overwritten.
- **Recovery is also a compare-and-swap.** A journal found at startup is recovered before anything else, but a
  backup is restored only if the file still matches the *installed candidate*. If it does not, someone edited it
  after the crash: stop, report both hashes, ask. Never overwrite newer work to finish an old rollback.

Per-file replacement is atomic. A batch is **recoverable, not atomic** — stated plainly rather than implied.

### Where transaction state lives

Journals and backups are **per-host transient state**, never in the knowledge base. The knowledge base is
committed and shared; a journal describes one interrupted run on one machine, and a backup is a copy of
somebody's source file. Neither belongs in a repository.

They go to the platform's state directory — `%LOCALAPPDATA%\mem-cleaner\` or `$XDG_STATE_HOME/mem-cleaner/` —
keyed by a digest of the knowledge base path, so two bases on one machine never share state.
`MEM CLEAN STATUS` prints the location.

### After an interruption

A journal left on disk means a run did not finish. **Every other command refuses until it is resolved**, because
reporting on a tree that is mid-transaction would describe a state nobody intended:

```text
<interpreter> .../runner/cli.py recover
```

Recovery restores what it safely can and **refuses what it cannot**. A file edited since the interrupted run
installed its candidate is left exactly as it is, with both hashes reported, and the journal stays on disk until
a human resolves it. Finishing an old rollback over newer work is the one outcome that is never acceptable.

### Minimum validation

Unconditional, in the transaction core, before any replacement is kept:

| Check | Rejects |
|---|---|
| non-empty | Content became nothing — the signature of a provider that crashed after opening its output |
| encoding | A candidate that is not valid UTF-8 |
| line endings | CRLF that became LF, or either that became mixed |
| trailing newline | A final newline added or removed — a real diff in every review tool, and never what was asked for |
| syntax | A file that no longer parses, where a parser exists |

Where no parser exists for the file type, that is reported as **unchecked**, not as valid. A pipeline needing a
stronger guarantee escalates; it must not read silence as success.

## Providers

A provider declares what it can do; the engine never knows what it is. See
[PROVIDER.template.md](PROVIDER.template.md) and [providers/index.md](providers/index.md).

Provider selection is **not** an installation question. Where only one provider can satisfy the configured
pipeline there is nothing to choose, and asking would imply a choice that does not exist. The question is raised
when it becomes real — a pipeline with a rewrite stage and more than one available candidate — with availability
shown per candidate and an `other` option that opens the custom-provider path.

> Ask at the moment a choice becomes real, not at the moment it becomes imaginable.

### Availability is not a path check

| Component | Location model | "Available" means |
|---|---|---|
| The runner | Ships inside this extension | A usable Python interpreter exists on this host |
| A provider invoked as a command | Wherever its own installer put it | The command resolves and answers a version probe |
| A provider shipping as a standalone binary | A tools root, `<tool-id>/<version>/` | The path exists and answers a version probe |

The runner has no environment of its own, because nothing installs it separately. What varies per machine is the
**interpreter it runs under**, and `custom/host/<host>.md` records the resolved one: a host with several Python
installations can satisfy a probe under one and not another, and a probe against the wrong one reports a state
true of nobody.

If `mem-toolbox` is installed it can attest the **executable** — path, version, present on this host. It cannot
attest adapter readiness or runner compatibility. Those are recorded here. The integration is preferred, never
required.

**The agent must never install a provider or the runner.** A missing one is reported with its upstream URL.

### Custom providers

A custom definition may declare a CLI provider. Requirements:

- `command` and `args` are an **argv vector**. No shell string, no interpolation beyond the documented
  variables, and each variable substitutes as a single argument;
- the id is namespaced `custom/<id>` and may not shadow a distributed id;
- approval binds **the resolved implementation**, not the front matter:

| Declared artifact | Bound by |
|---|---|
| A repository-relative script or directory | Content hash of the file, or of the tree |
| A binary outside the repository | Resolved absolute path, reported version, **and the executable's content hash** — a path and a version bind nothing, since a binary can be replaced while reporting the same version |
| An interpreter whose dependency closure cannot be determined (`python`, `node`, a shell) | **Not bindable** — confirmation on every run, and never eligible for `automatic` |

A changed bound value lapses the approval, and `automatic` falls back to `manual` until it is renewed.

## Provenance

Two different things hide under "watermark". Invisible Unicode markers and generator strings in code are
defects. **Provenance metadata is not a defect** — removing it removes attribution.

`metadata` is therefore not one capability:

| Capability | Contents | In `safe`? |
|---|---|---|
| `metadata-technical` | Generator and tool-version strings, build timestamps, editor artefacts — an **allowlist**, enumerated in the provider definition, never a wildcard | Yes |
| `metadata-attribution` | Author, copyright, licence, contact, identity fields in EXIF, XMP or document properties | **No** |
| `c2pa` | Content Credentials assertions and manifests | **No** |

The allowlist is load-bearing: `safe` removes only fields named in advance, so a provider gaining a broader mode
upstream cannot widen `safe` by surprise.

For `metadata-attribution` and `c2pa`:

- excluded from `safe` and from every default pipeline;
- excluded from wildcard automation — never under `automatic` against a glob, and requiring both a pipeline that
  names the stage and a target that names the file;
- each run reports **what was removed**, and states that **removal is not proof of absence**: soft bindings and
  embedded identifiers may remain. The tool cannot claim a file carries no provenance.

These constraints travel in the provider schema as data, so the validator enforces them rather than relying on
this page being read.

## Reporting

Report what ran, what changed and what was refused — never file contents. A stage that made no change says so.

With `extensions_cleaner_update_daily_log: true`, write one concise line, never per-file detail:

```markdown
- mem-cleaner processed 4 files with the `safe` pipeline; 1 skipped (edited after the agent wrote it).
```

## Boundary with other extensions

`mem-toolbox` answers "which tool, and is it here". `mem-cleaner` answers "what should happen to a file after
it is written, and under what guarantee". If the question is *may I run this, and how*, it belongs to the
toolbox; if it is *what runs over my output, unattended*, it belongs here.
