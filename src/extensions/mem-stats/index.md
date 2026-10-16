# Extension: `mem-stats`

Measures what agent sessions really consume, from the client's own local logs: tokens per request (new, read from
the cache, written to it, output), what fills the context (MEM and each extension, tool results, attachments, fixed
overhead such as tool definitions), where the cache was rebuilt and why, compactions and fresh starts — per project
and for the whole host. It makes no model calls and sends nothing anywhere: everything stays in one local SQLite
ledger per user that holds counts, never content.

- **version**: 0.1.1
- **provides**: `STATS`
- **subcommands**: `SETUP`, `STATUS`, `RESET`, `REPORT`, `WATCH`, `INGEST`, `PRUNE`, `INIT`, `INVENTORY`, `READ` -
  closed set
- **precedence**: base
- **external actions**: no
- **executable content**: yes - `runner/stats.py`, `runner/claude_code.py`, `runner/codex.py`,
  `runner/hook_ingest.py`, `runner/setup.py`
- **default mode**: may-write (settings files, only after the user confirms the plan)
- **clients**: Claude Code (CLI and VS Code extension); Codex (CLI and app; its VS Code extension on Windows runs no
  hooks while openai/codex#33413 is open — ingest there by hand with `MEM STATS INGEST`)

## Commands

| Command | What it does |
|---|---|
| `MEM STATS SETUP` | Runs the setup wizard: two questions, the full plan, one confirmation. Installs the ingestion hook, creates the ledger, imports the history. Run again to change the answers |
| `MEM STATS STATUS` | Hooks present per client, ledger path and size, last ingestion, lock and queue. Read-only |
| `MEM STATS RESET` | Removes the hooks mem-stats added, and only those; the ledger stays unless the user asks to delete it |
| `MEM STATS REPORT` | The report, as readable text (`--format text`) or JSON; filters by project, period, session; chooses sections |
| `MEM STATS WATCH` | The report, rendered again whenever the ledger changes: a live local view |
| `MEM STATS INGEST` | Imports by hand: a whole host's history, one workspace, one transcript or rollout |
| `MEM STATS PRUNE` | Deletes whole sessions last active before a date |
| `MEM STATS INIT`, `INVENTORY`, `READ` | Create the ledger; snapshot a KB's extensions; an instrumented full read of a KB file |

Python 3.11+ and standard-library SQLite. Codex rollouts older than a week (recompressed by Codex to `.jsonl.zst`)
need Python 3.14+, whose standard library reads zstd; with an older Python they are skipped and counted under
`coverage`. Exact tokenization needs tiktoken; without it sizes are labelled character estimates. Independent of
mem-optimize.

## When executable content is not allowed

Every subcommand runs code under `runner/`. When this extension is loaded or invoked, or the user asks to install
it, and `extensions_allow_executable_content` is not `true` in `MEM.config.md` (absent means `false`), the agent
**must not** run `runner/` and **must**:

1. tell the user that the setting is off, and that MEM therefore forbids running this extension's code;
2. say plainly what follows: **while the setting stays `false`, mem-stats is installed but does not work** —
   nothing is collected, no report can be produced, and the wizard cannot run;
3. ask for authorization to set `extensions_allow_executable_content: true`, naming the five runners as the code
   that would then run, and noting that the setting covers every installed extension declaring executable content;
4. change `MEM.config.md` only after an explicit yes. On a no, run nothing and do not ask again in the session.

Asking is not authorization: until the user answers yes, the setting and the runners stay as they are.

## Setup wizard (`MEM STATS SETUP`)

Run after installation. Registering the extension alone collects nothing: the wizard is what starts collection. Ask
with the client's question tool (`AskUserQuestion` in Claude Code; `request_user_input` in Codex, Plan mode only —
numbered questions otherwise), recommended option first, in the user's language, explaining each plainly. Write
nothing until the final confirmation.

0. **Executable content** — only if off: as in the section above. Without it the wizard stops.
1. **Clients** (multi-select) — Claude Code · Codex, pre-selecting those installed (`~/.claude/`, `~/.codex/`).
   Explain that Codex runs a new or changed hook only after the user approves it with `/hooks` (CLI) or the app's
   hook review.
2. **Import the history** — yes (recommended) · no. Yes reads every past session of the chosen clients on this host
   once, at installation, in the foreground; say it may take a few minutes on a long history.

There is no scope question: there is **one ledger per user, for every project**. Each request records the project it
belongs to (the folder its session started in), so `REPORT --project PATH` gives any project's figures and a
per-project ledger would add nothing.

Then write the answers to a JSON file (`{"clients": ["claude", "codex"], "backfill": true}`; advanced, rarely needed:
`ledger`, `python`, `adapter_python` — e.g. a Python 3.14 for old Codex rollouts), show
`runner/setup.py plan --answers FILE` to the user, and on confirmation run `runner/setup.py apply --answers FILE`.
`apply`:

- copies the runners to `~/.mem/mem-stats/<version>/runner/` (run `apply` again after updating the extension);
- creates the ledger `~/.mem/mem-stats/state/stats.sqlite`;
- backs up each settings file to `~/.mem/mem-stats/backups/<stamp>/` and records what it added in
  `~/.mem/mem-stats/setup-log.json`;
- adds the hook — Claude Code: `Stop` and `SessionEnd` in `~/.claude/settings.json`; Codex: `Stop` in
  `~/.codex/hooks.json` — recognized by its runner name, so a second `apply` replaces instead of duplicating and other
  tools' hooks (mem-optimize's included) are never touched;
- imports the history when chosen.

`STATUS` is `setup.py status`; `RESET` is `setup.py reset` (`--delete-ledger` only on an explicit request).

## How collection works

At the end of every agent turn the hook queues the session's transcript (Claude Code) or rollout (Codex) and returns
at once, printing nothing: it costs no model tokens. A background worker — one at a time per ledger, under a lock —
waits a few seconds for the client to finish writing, then runs the adapter on the queued files. Several sessions open
at once only queue; the ledger is SQLite in WAL mode with deterministic event ids, so concurrent writers never
duplicate an event. A queued file leaves the queue only once its import succeeded: a failed one is retried by the
next worker runs, at most three, then dropped with a line in the run log. The history import at setup takes the same
lock, waiting for a running worker first. The run log `~/.mem/mem-stats/state/ingest.jsonl` records times, exit
codes and counts, never content. Every process starts without a visible window.

Re-ingesting is safe. A measured `usage` event arriving again with the same token counts replaces the stored one
(older ledgers gain new fields this way); with different counts it is a conflict, counted and skipped, never an abort.
Derived events (attribution, composition, breakdown, coverage...) are replaced by the latest run, except that a run
with less context — fewer KB roots — never overwrites richer data.

## Reports

`runner/stats.py --db LEDGER report` (`watch` takes the same options plus `--interval`):

- `--format text` — Markdown, one heading per section; `json` is the default.
- `--sections a,b` — any of `provider_usage`, `projects`, `mem_attribution`, `money`, `context_composition`,
  `fixed_overhead`, `kb_pages`, `cache_breaks`, `costliest`, `lifecycle`, `subagents`, `coverage`,
  `extension_metrics`, `extensions`, `payload`, `inventory_by_session`.
- `--project PATH` (that folder and below), `--since` / `--until` (ISO, UTC unless a zone is given; `until`
  exclusive), `--session`, `--top N` (ranked lists, default 10), `--prices CARD`, `--attribution-method NAME`,
  `--kb-root KB` (checks inventory snapshots against the KB's current registry).

What the sections hold:

- `provider_usage`, `money` — tokens by bucket (input, cache reads, 5m and 1h cache writes, output), per client and
  model; API-equivalent cost with a price card. Unknown is null, never zero.
- `projects` — per project: sessions, requests, tokens, cost, MEM share.
- `mem_attribution` — MEM's share of input (Claude Code), against total and against non-MEM input.
- `context_composition` — prompt tokens by source, `new` versus `carried` (repeated, paid as cache reads):
  `assistant_output`, `user_message`, `attachment:<type>` (with a `user_attachments_total`), `tool:<name>`,
  `tool:mcp:<server>`; tool results bearing the sqz compressor's markers are counted under `processed.sqz`.
- `fixed_overhead` — system prompt, tool definitions and listings carried by every request. `tool_usage` gives, per
  tool, its definition weight, calls, `calls_per_1000_requests` and `last_called`; `loaded_never_called` and
  `rarely_called` (at most one call per 1,000 requests carrying the tool) list the candidates to disable.
- `kb_pages` — the KB pages that cost most (`<shell>`, `<search>`, `<instructions>` for access not tied to one page).
- `cache_breaks` — requests that rewrote at least half of a 10k+ prompt, by likely cause (`idle_over_1h`,
  `idle_over_30m` for OpenAI, `idle_over_5m`, `model_changed`, `context_reduced`, `other`), with the cost of the
  rewrite against reading from the cache.
- `costliest` — top sources, pages and overhead items in one place; overlapping views, not parts of a total.
- `lifecycle` — compactions (trigger, context before and after) and `/clear` fresh starts.
- `subagents` — delegated runs by agent type: runs, requests, tokens, cost.
- `coverage` — what the adapters could not account for: pending and interrupted requests, anomalies, inconsistent
  buckets, untested client versions, skipped rollouts, conflicts; inventory snapshots older than the registry.
- `extension_metrics` — numeric metrics other extensions report (below).

## Ingesting by hand (`MEM STATS INGEST`)

The adapters write to the ledger with `--db LEDGER`, or print JSONL for `stats.py ingest` (stdin; a rejected line is
reported as `line N: reason`, the others are kept, exit code 1 if any was rejected).

- `runner/claude_code.py` — Claude Code transcripts (`~/.claude/projects/`, subagent transcripts included; the CLI
  and the VS Code extension share them): `--all`, `--workspace DIR`, `--transcript FILE`, `--session ID`;
  `--kb-root KB` (repeatable) for MEM attribution, also found under `--workspace`; `--find-kb` looks for KB roots
  under each session's own project folder (as the hook and the history import do; `.git`, `.tmp`, `node_modules`
  and virtual environments are skipped). Requests already stored by the
  same adapter revision and settings are skipped (every line is still read, since the context chain needs it);
  `--full` recomputes them.
- `runner/codex.py` — Codex rollouts (`$CODEX_HOME/sessions/` and `archived_sessions/`, default `~/.codex`):
  `--all`, `--workspace DIR`, `--rollout FILE`, `--session ID`.

`--help` on each runner gives the full syntax.

**Claude Code** gives `usage` per request (settled requests only: a request without `stop_reason` after the quiet
period is kept with `output_final: false` and its output is a lower bound — mostly subagent requests whose transcript
kept only early streaming usage, counted as `requests_output_not_final`), MEM `attribution` (method `claude-code-positional/1`: segments sized on
measured usage, earlier answers by their `output_tokens` since thinking stays in context, messages preserved across a
compaction followed into the next requests), `composition`, `breakdown` and `overhead`, `lifecycle` and `coverage`.
**Codex** gives `usage` (input already includes cached input; reasoning tokens kept apart; a response logged twice on
resume, in the same or another file, counts once), `lifecycle` and `coverage`. MEM attribution and composition are
Claude Code only: a known limit.

## Ledger and privacy

Event kinds: `usage`, `attribution`, `composition`, `breakdown`, `overhead`, `lifecycle`, `coverage`, `metric`,
`delivery`, `inventory`. Every kind has a **closed set of fields**: an unknown field is rejected, identifiers are
bounded and contain no spaces, paths no control characters. The ledger therefore cannot hold file contents, prompts,
answers, credentials or tool output; it holds identifiers, counts, modes, hashes, KB page paths, tool names and
project folders. Local collection makes no LLM calls; a report costs tokens only when it is put into a conversation.

`PRUNE --before DATE` deletes whole sessions whose latest event is older, never half a session.

## Extension metrics

Another extension may record numeric metrics as `metric` events: `extension` (its id), `name`
(`<extension-id>.<metric>`, lowercase, dots and underscores), `version` (integer, the metric's definition), `value`
(a number, never text), optional `unit` (`count`, `tokens`, `seconds`, `bytes`, `usd`...), `at`, optional `session`.
REPORT aggregates them by name under `extension_metrics`.

## Price cards

`prices/` holds an Anthropic API card copied from the official pricing page; a card is a JSON list of entries with
`provider`, `model`, `currency`, `as_of`, optional `until`, `basis` (e.g. `api-equivalent`), the per-million rates
(`input`, `cached_input`, `cache_write`, `cache_write_1h`, `output`) and optional tier keys (`service_tier`, `speed`,
`inference_geo`). Each request takes the matching card with the latest `as_of` not after it; a request older than
every matching card takes the earliest one and is counted as priced before the card's date; a request whose rates are
missing is unpriced and counted by reason. Under a subscription plan the totals value usage at API rates: they are
not what was paid.

## Files

- `runner/` — the five runners; `prices/` — base price cards.
- `custom/` — the project's own price cards, preserved by updates. The ledger is not in the KB: it lives in
  `~/.mem/mem-stats/state/` with the run log, lock and queue.
