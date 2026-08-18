# `MEM CLEAN`

- **mode**: may-write
- **subcommands**: `SAFE`, `FULL`, `TEST`, `STATUS`, `PROVIDERS`, `PIPELINES` — closed set
- **shell**: through the runner only
- **external**: no

Runs configured post-processing over files, or reports what would run.

## Surface

| Form | Arity | Semantics | Replaces the target |
|---|---|---|---|
| `MEM CLEAN` | 0 | Configured pipeline over this session's changed files | yes |
| `MEM CLEAN <target>` | 1 | Configured pipeline over an explicit target | yes |
| `MEM CLEAN SAFE <target>` | 1 | Deterministic stages only | yes |
| `MEM CLEAN FULL <target>` | 1 | Complete pipeline, including a rewrite stage if configured | yes |
| `MEM CLEAN TEST <target>` | 1 | Run the pipeline transactionally and report | **no** |
| `MEM CLEAN STATUS` | 0 | Configuration, versions, compatibility | no |
| `MEM CLEAN PROVIDERS` | 0 | Providers, roles and availability | no |
| `MEM CLEAN PIPELINES` | 0 | Available pipelines and their stages | no |

The column says **replaces the target**, not "writes". `MEM CLEAN TEST` guarantees the target is unchanged; it
does not guarantee the run has no side effects, because a formatter, a build or a test suite can emit artefacts,
touch caches and write logs unless isolated. Only `STATUS`, `PROVIDERS` and `PIPELINES` write nothing at all.

## Resolving the first token

The subcommand set above is **closed**. Resolution follows `MEM.md`, "Subcommands":

1. the token matches a declared subcommand → it is the subcommand;
2. otherwise → it is the target.

A target beginning with `./` is **always** a target: `MEM CLEAN ./STATUS` operates on the file named `STATUS`.
Use it whenever a path could be mistaken for a keyword.

## Acknowledgement

Every activation opens with an acknowledgement line, and it names the pipeline, because the pipeline is what
determines whether anything irreversible can happen:

```markdown
> MEM CLEAN: active (pipeline `safe`, mode `manual`)
```

Disclose on first use in a session when a stage resolves to a custom provider.

## Before running anything

1. **`extensions_cleaner_enabled: false` or `extensions_enabled: false`** → report and stop.
2. **No runner installed** → report it, name the upstream source, and stop. This is an ordinary state, not an
   error, and `STATUS`, `PROVIDERS` and `PIPELINES` still answer.
3. **Incompatible runner** → refuse to run. Never fall back to a best-effort subset; report both versions and
   the verdict.
4. **Pipeline invalid** — more rewrite stages than `extensions_cleaner_max_rewrite_stages`, a stage whose
   capability no available provider satisfies, a custom id shadowing a distributed one — → refuse, naming the
   stage.

## Choosing the files

Without a target, the set is the session's attribution record: files **this agent** changed, each with the hash
captured after its last write. A file whose hash no longer matches is **skipped and reported** — a human edited
it since.

Never derive the set from `git diff`.

With a target, the target is used as given. An explicit target is a user instruction, and it may name a file the
agent never touched.

## Running

```text
inspect → transform … → rewrite (at most one) → format → validate
```

Everything happens on a working copy under a journal. The original is replaced only after validation passes; on
failure `extensions_cleaner_fail_policy` decides, and its default is `restore`.

In `automatic` mode this runs **before reporting the work complete**, after the test suite is green.

## Reporting

Report per stage: what ran, how many changes, what was skipped and why. Report refusals with their reason.
**Never report file contents.**

```text
MEM Cleaner — src/player.gd, pipeline `safe`

[1/3] unicode            2 changes
[2/3] metadata-technical no changes
[3/3] validate           syntax ok

Result: updated
```

A failure reports what was restored, and says plainly that the file is as it was.

## Refusals this command makes

These are correct behaviour, not errors, and each is reported rather than worked around:

- a file edited since the agent wrote it;
- an escalation that cannot be satisfied because no test command is configured;
- a pipeline exceeding the rewrite limit;
- a custom provider whose bound implementation changed since approval;
- a custom provider that cannot be bound at all, under `automatic`;
- `metadata-attribution` or `c2pa` reached through a glob rather than an explicit target and an explicit stage;
- an incompatible runner.

## Never

- Install the runner, a provider, or anything else.
- Claim a file was AI-generated on the basis of style or heuristics.
- Clean a file mid-task. There is no per-write trigger, deliberately.
- Report success when validation was skipped. Say which guarantee actually held.
