# Extension: `mem-stats`

Measures what agent sessions really consume, from the client's own local logs: tokens per request (new, read from
the cache, written to it, output), what fills the context (MEM and each extension, tool results, fixed overhead such
as tool definitions), where the cache was rebuilt and why, compactions and fresh starts. It makes no model calls
and sends nothing anywhere: everything stays in a local SQLite ledger that holds counts, never content.

- **version**: 0.1.0
- **provides**: `STATS`
- **subcommands**: `INIT`, `INVENTORY`, `READ`, `INGEST`, `REPORT`, `WATCH`, `PRUNE` - closed set
- **precedence**: base
- **external actions**: no
- **executable content**: yes - `runner/stats.py`, `runner/claude_code.py`, `runner/codex.py`
- **default mode**: may-write
- **clients**: Claude Code (CLI and VS Code extension); Codex (CLI, app and VS Code extension)

| Command | What it does |
|---|---|
| `MEM STATS INIT` | Creates the ledger |
| `MEM STATS INGEST` | Reads the client logs into the ledger (Claude Code: `runner/claude_code.py`; Codex: `runner/codex.py`) |
| `MEM STATS REPORT` | Usage, context composition, fixed overhead, KB pages, cache breaks, lifecycle, costliest items; `--since`/`--until`, `--prices` |
| `MEM STATS WATCH` | The report, re-emitted when the ledger changes: for a local dashboard |
| `MEM STATS PRUNE` | Deletes whole sessions last active before a date |
| `MEM STATS INVENTORY`, `MEM STATS READ` | Snapshot of the KB's extensions; an instrumented full read of a KB file |

Independent of mem-optimize. Python 3.11+ and standard-library SQLite; reading Codex rollouts older than a week
(recompressed by Codex to `.jsonl.zst`) needs Python 3.14+, whose standard library reads zstd — with an older
Python they are skipped and counted in the coverage summary. Explicit tokenization also needs tiktoken. Registering
this extension alone does not start collection: initialize a project-owned database under `custom/` and run the
adapters.

## When executable content is not allowed

Every subcommand and adapter runs code under `runner/`. When this extension is
loaded or invoked, or the user asks to install it, and
`extensions_allow_executable_content` is not `true` in `MEM.config.md`
(absent means `false`), the agent **must not** run `runner/` and **must**:

1. tell the user that the setting is off, and that MEM therefore forbids
   running this extension's code;
2. say plainly what follows: **while the setting stays `false`, mem-stats is
   installed but does not work** — no usage, attribution or composition is
   collected, no report or dashboard can be produced, and the Claude Code
   adapter cannot read transcripts;
3. ask for authorization to set `extensions_allow_executable_content: true`,
   naming `runner/stats.py`, `runner/claude_code.py` and `runner/codex.py` as the code that would
   then run, and noting that the setting covers every installed extension
   declaring executable content;
4. change `MEM.config.md` only after an explicit yes. On a no, run nothing and
   do not ask again in the same session.

Asking is not authorization: until the user answers yes, the setting and the
runner stay as they are.

## Behavior

The collector must distinguish tool-payload counts from cumulative provider
usage. Exact billing requires provider request IDs, usage with separate cache
buckets, and a dated price card. Without those inputs, report unknown fields
as null; do not infer exact cost or the cost of a hypothetical session without MEM.

Inventory is the union of the supplied MEM catalogue, local EXT.md registrations
and installed entrypoints. Report configured status, effective activation,
executable permission and per-extension observations, including unobserved
active extensions. A missing catalogue means local-only coverage.

The event ledger belongs to this extension. It must not contain file contents,
user prompts, credentials or model answers. Store identifiers, counts, modes,
hashes, state snapshots and usage attribution only. Local collection makes no
LLM calls; instructions and reports consume tokens when included in context.
WATCH is suitable for a local dashboard; sending every update to a model would
increase token consumption.

## Commands

`--db PATH` is mandatory. INIT creates the ledger; INGEST reads JSONL on stdin;
INVENTORY snapshots a KB with optional `--manifest PATH`; READ instruments a
full file read. REPORT and WATCH accept a session filter and `--prices PATH`.
WATCH polls for changes and emits JSON only when the ledger changes. PRUNE takes
`--before DATE`.

The adapter must normalize provider usage, count repeated context per request,
and supply MEM/extension attribution; the runner cannot discover that from
an editor's UI or from the model's final answer.

## Client adapters

`runner/claude_code.py` is the first client adapter, read-only and offline. It
parses Claude Code transcripts (`~/.claude/projects/<workspace>/`, including
subagent transcripts; the VS Code extension and the CLI share them) and emits
`usage` events: inclusive input, cache reads/writes with the 1h share in
`usage_detail`, pricing tier, server tool counts, client version and entrypoint.
Pipe its stdout into INGEST or pass `--db`. Re-runs are idempotent: a request is
emitted only once settled, and its coverage summary (stderr) reports pending,
inconsistent, unrecognized and untested-version lines.

With a KB root (`--kb-root`, or found under `--workspace`) it also emits one
`attribution` event per request, method `claude-code-positional/1`: MEM and
per-extension buckets with input categories (`instructions`, `kb_tool_results`,
`kb_writes`). The prompt is the request's `parentUuid` chain. Sizes are calibrated
on measured usage: earlier answers occupy their `output_tokens` (thinking stays in
context although transcripts keep almost none of its text), and lines added
between two requests occupy `ΔI - previous output`, shared out by estimate.
Segments are placed backwards from the prompt's end and split over the cached,
written and uncached ranges. MEM content is: tool calls on KB paths (Bash and
PowerShell when the command names the KB or runs inside it), writes into the
KB, and injected instruction files inside a KB or naming `MEM.index.md` /
`MEM.config.md`. The coverage summary reports measured versus fallback groups
and the unexplained prefix (system prompt and tools), whose stability is the
quality signal. Messages preserved across a compaction are not followed yet.

Attributions are estimates kept apart from measured usage, so a revised method
is added under a new method name instead of rewriting events. REPORT uses the
latest attribution per request, or `--attribution-method NAME`.

Unless `--no-composition`, the adapter also emits one `composition` event per
request: calibrated prompt tokens by source (`assistant_output`,
`user_attachments`, `tool:<name>`, `tool:mcp:<server>`), each split into `new`
(entered since the previous request) and `carried` (repeated, i.e. paid as cache
reads), plus `processed.sqz` for tool results bearing the markers of the sqz
output compressor (`[Abbreviations]`, `sqz expand <hash>`, `§ref:…§`; absence
proves nothing), so that its effect on a context stays visible.
It needs no KB root. REPORT aggregates it as `context_composition`, and
`--since` / `--until` (ISO, `until` exclusive) restrict a report to a period,
for before/after comparisons.

With composition, the adapter also emits one `breakdown` event per request and
the `overhead` events it names. An `overhead` event records fixed per-request
content once: the system prompt and each tool definition from Claude Code's
`prompt_snapshot` attachments (character estimates), or a listing attachment
that every later request carries (`skill_listing`, `agent_listing_delta`,
`deferred_tools_delta`, `mcp_instructions_delta`, `instructions`; calibrated).
A `breakdown` names the overhead in force, the unexplained prefix, the tools the
request called, and — with a KB root — KB pages by new and carried tokens
(`<shell>` and `<search>` for commands and searches inside a KB, `<instructions>`
for a MEM pointer in an instruction file outside it). REPORT adds:

- `fixed_overhead`: each item's replayed tokens (size × requests carrying it,
  snapshot sizes scaled to the prefix of the first request they served), calls
  per tool, MCP servers, tools loaded but never called, and `tool_usage`: every
  tool seen with its calls and the cost of its definition (a tool called but
  never in a snapshot was deferred or not recorded);
- `kb_pages`: the costliest KB pages, ranked;
- `cache_breaks`: later requests in a stream (a session or one subagent) that
  rewrote at least half of a prompt of 10k+ tokens, by likely cause
  (`idle_over_1h`, `idle_over_30m` (OpenAI), `idle_over_5m`, `model_changed`, `context_reduced` — which
  includes compactions — or `other`), with the API-equivalent cost of the
  rewrite against reading the same tokens from the cache when a card matches;
- `costliest`: the top sources, KB pages and overhead items in one place. The
  three lists overlap; they are views, not parts of a total.

- `lifecycle`: compactions (trigger, median context before and after) and fresh starts with `/clear`, from Claude
  Code's `compact_boundary` and `local_command` lines and Codex's `compacted` lines.

Ranked lists are ordered largest first; `--top N` (default 10) bounds them.

`runner/codex.py` reads Codex rollouts (`$CODEX_HOME/sessions/` and `archived_sessions/`, default `~/.codex`):
one `usage` event per `token_usage_record` (Codex's `input_tokens` already includes cached input; reasoning tokens,
part of the output, are kept apart), or, in rollouts older than that record, per change of the cumulative
`token_count`; the model comes from the latest `turn_context`. A response logged twice on resume counts once. It
emits `lifecycle` compactions too; MEM attribution and composition are Claude Code-only for now. `--workspace`
keeps the sessions whose working folder it is. For OpenAI, cache breaks count input not read from the cache as
rewritten (no cache-write figure is reported) and add `idle_over_30m`, OpenAI's cache lifetime for GPT-5.6+.

`PRUNE --before DATE` deletes whole sessions whose latest timed event is older, never half a session; overhead
events still referenced by kept requests stay.

Price cards may add `cache_write_1h` and tier keys (`service_tier`, `speed`,
`inference_geo`, defaulting to standard/standard/global). A request whose 1h
writes or tier have no matching rate is unpriced rather than priced at a guess.
`basis` (e.g. `api-equivalent`) is echoed in reports. `prices/` holds a dated
Anthropic API card copied from the official pricing page; under a subscription
plan its totals value usage at API rates and are not what was paid. The adapter
records `inference_geo: "not_available"` as unreported (default pricing).

Project databases, price cards and adapter settings live under `custom/` and
must be preserved by updates. Full protocol and examples are in the source
bundle README; use `runner/stats.py --help` for executable syntax.
