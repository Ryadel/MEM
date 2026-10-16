# Extension: `mem-optimize`

Keeps long agent sessions from wasting tokens. Every request re-sends the whole conversation, so a session that has
grown large, or that resumes after the prompt cache expired, costs far more than a fresh one that re-orients from the
knowledge base. mem-optimize watches the session's size, tells the agent when a restart pays, carries the work into
the fresh session, and stops the first prompt after a long pause before it rewrites the whole context into the cache.

- **version**: 0.1.0
- **provides**: `OPTIMIZE`
- **subcommands**: `SETUP`, `STATUS`, `RESET`, `PAGES` - closed set
- **precedence**: base
- **external actions**: no
- **executable content**: yes - `runner/hook_prompt.py`, `runner/hook_session.py`, `runner/wizard.py`,
  `runner/pages.py`
- **default mode**: may-write (settings files, only after the user confirms the plan)
- **clients**: Claude Code (CLI and VS Code extension); Codex (CLI and app; its VS Code extension on Windows runs no
  hooks while openai/codex#33413 is open — check before relying on it there)
- **customization**: `custom/` holds the setup log, settings backups and, for the project scope, runtime state.

## Commands

| Command | What it does |
|---|---|
| `MEM OPTIMIZE SETUP` | Runs the setup wizard: asks which components to enable and where, shows the full plan, writes it after one confirmation. Run again to change the answers |
| `MEM OPTIMIZE STATUS` | Shows what mem-optimize has installed in each settings file: hooks, disabled tools, allow rules. Read-only |
| `MEM OPTIMIZE RESET` | Removes everything mem-optimize added, and only that. Backups of the settings files stay in `custom/backups/` |
| `MEM OPTIMIZE PAGES` | Lists the knowledge base pages that weigh most on sessions, with a maintenance suggestion for each. Needs mem-stats; read-only: it never edits a page |

## Components

| Component | What the user sees | Cost |
|---|---|---|
| **Advisor** | Silent below the threshold (default 400k tokens of context). Above it the agent says, once, at a natural breakpoint, that a restart would pay; again past the insist threshold (600k) | One interpreter start per prompt; no tokens below the threshold |
| **Guided restart** | Only after the user agrees, the agent updates the KB's resume point, writes a short handoff note and asks for `/clear`; the fresh session opens by confirming the note was restored | The note, a few thousand characters |
| **Long-pause stop** | After a pause longer than the prompt cache lasts, on a context of 200k+ tokens, the first prompt is stopped once with a message offering (A) `/clear`, the message being carried into the fresh session with a snapshot of the last exchanges, or (B) sending again to continue here | Nothing is sent to the model when stopping |
| **After a compaction** | When the client compacts the conversation, a short pointer tells the agent to re-read the KB index and the latest resume point: the summary stays the reference for the work in progress, the KB for decisions and conventions | A few hundred characters, once per compaction, plus the two re-reads |
| **Unused tools** | Built-in tools the user never calls are disabled, so their definitions leave every request | Takes effect in a new session |

Thresholds are configurable. The advisor and the stop read the session transcript; they send nothing anywhere.

## When executable content is not allowed

Every component is code. When this extension is loaded or invoked, or the user asks to install it, and
`extensions_allow_executable_content` is not `true` in `MEM.config.md` (absent means `false`), the agent **must not**
run any runner and **must**:

1. tell the user that the setting is off, and that MEM therefore forbids running this extension's code;
2. say plainly what follows: **while the setting stays `false`, mem-optimize is installed but does nothing** — no
   advice, no restart carry-over, no stop after a long pause, and the wizard cannot run;
3. ask for authorization to set `extensions_allow_executable_content: true`, naming the four runners as the code
   that would then run, and noting that the setting covers every installed extension declaring executable content;
4. change `MEM.config.md` only after an explicit yes. On a no, run nothing and do not ask again in the session.

## Setup wizard (`MEM OPTIMIZE SETUP`)

Run after installation, and whenever the user wants to change the answers. Ask with the client's question tool
(`AskUserQuestion` in Claude Code; `request_user_input` in Codex, Plan mode only — numbered questions otherwise),
recommended option first, in the user's language. **Explain every question
plainly**: what the option does, what it costs, what changes if refused. Write nothing until the final confirmation.

0. **Executable content** — only if off: as in the section above. Without it the wizard stops.
   **Clients** (multi-select) — Claude Code · Codex, pre-selecting those installed (`~/.claude/`, `~/.codex/`).
   Explain that both receive the same hooks; that Codex runs a new or changed hook only after the user approves it
   with `/hooks` (CLI) or the app's hook review; and that questions 4 and 8 concern Claude Code only, since Codex
   has no equivalent of its tool and permission lists.
1. **Advisor** — on at 400k / 600k (recommended) · custom thresholds · off. Explain that it is silent below the
   threshold and what the advice looks like.
2. **Guided restart** — on (recommended) · off. Explain the flow: agreement, handoff note, `/clear`, the confirmation
   in the first reply of the fresh session.
3. **After a long pause** — stop the first prompt and propose `/clear` with the message carried over
   (recommended) · nothing. Explain that the stopped message is not lost, and that sending again continues here.
4. **Unused tools** (multi-select) — if mem-stats is installed, run its Claude Code ingestion and `report`, and use
   `tool_usage`: pre-select tools loaded but never or almost never called. For each, say **what the tool does**, its
   definition size and its calls. Never pre-select a tool the user called recently; never disable one not selected.
5. **Scope, one question per enabled element** (advisor, restart, stop, each tool, report permissions) — all projects
   (recommended) · only this project. All projects writes the user settings; only this project writes
   `<workspace>/.claude/settings.local.json`.
6. **Costs in the advice** — tokens plus the API-equivalent cost, labelled as such (recommended, needs mem-stats'
   price card) · tokens only. On a subscription the money is a valuation, not what is paid.
7. **After a compaction** — inject the re-orientation pointer (recommended) · nothing. Explain that the agent
   then re-reads the index and the resume point once, and that the client's summary keeps precedence for the work
   in progress.
8. **Reports without prompts** — allow `MEM OPTIMIZE STATUS` and mem-stats' `report` to run without asking
   (recommended) · ask each time. Read-only commands only: the wizard never pre-approves edits or other commands.

## Heavy pages (`MEM OPTIMIZE PAGES`)

Run mem-stats' REPORT (with `--since` for a recent period) and pass it to `runner/pages.py --kb-root <KB_ROOT>`. Show
the pages it lists — tokens carried, current size, suggestion — and offer to do the maintenance the user picks:
moving concluded history of a task to `tasks/done/` or a linked page, shortening a resume point, folding an accepted
draft into its ADR. **Never edit a page unasked**, and never shorten one by dropping decisions, rules or open items:
a lighter page that has lost a fact costs more than it saves.

Then write the answers to a JSON file in the agent's temporary folder (format in `runner/wizard.py`) and run:

```text
python -I -B runner/wizard.py plan --answers <file> --workspace <workspace> --kb-root <KB_ROOT> [--prices <card>] [--stats-db <ledger>]
```

Show the plan in full — every file, hook command, tool and rule — and ask **one** confirmation. On yes, run the same
command with `apply`. It backs up each settings file to `custom/backups/<timestamp>/` and records what it added in
`custom/setup-log.json`. If the client refuses the agent's write to its own settings (Claude Code may treat it as
self-modification), say so and ask the user to confirm explicitly; if it is still refused, show the exact JSON from
`plan --json` and where it goes. Tool changes take effect in a new session: with mem-stats installed, offer to check
`fixed_overhead` there.

## Guided restart (agent procedure)

When the advisor's context line asks for it, propose the restart **in one short line**, at a breakpoint — never in
the middle of a change. Only after the user agrees: update the KB's resume point when the project has a MEM KB;
write the handoff note to the path the advisor names (state, decisions made, next step, files to read; under 8,000
characters); then ask the user to type `/clear` and send any message. Never write the note unasked.

## Files

| Path | Content |
|---|---|
| `runner/hook_prompt.py` | `UserPromptSubmit` hook: advisor and long-pause stop |
| `runner/hook_session.py` | `SessionStart` hook (`clear`): injects the handoff note, or the held message and its snapshot |
| `runner/wizard.py` | `plan`, `apply`, `reset`, `status` |
| `runner/pages.py` | `MEM OPTIMIZE PAGES`: heavy pages from a mem-stats report, with suggestions |
| `custom/setup-log.json`, `custom/backups/` | What setup added, and the settings files as they were |
| `custom/state/` (project scope) or `~/.mem/mem-optimize/state/` (all projects) | Runtime state: advisor state, held prompt, handoff note, logs without content. Self-ignoring `.gitignore`: never committed |

For all projects, setup copies the runners to `~/.mem/mem-optimize/<version>/runner/`, so the hooks do not depend on
one project's KB.
