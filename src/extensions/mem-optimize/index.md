# Extension: `mem-optimize`

Keeps long agent sessions from wasting tokens. Every request re-sends the whole conversation, so a session that has
grown large, or that resumes after the prompt cache expired, costs far more than a fresh one that re-orients from the
knowledge base. mem-optimize watches the session's size, tells the agent when a restart pays, carries the work into
the fresh session, and stops the first prompt after a long pause before it rewrites the whole context into the cache.

- **version**: 0.3.1
- **provides**: `OPTIMIZE`
- **subcommands**: `SETUP`, `STATUS`, `RESET`, `PAGES` - closed set
- **precedence**: base
- **external actions**: no
- **executable content**: yes - `runner/hook_prompt.py`, `runner/hook_session.py`, `runner/clients.py`,
  `runner/wizard.py`, `runner/pages.py`, `runner/opencode-plugin.js`
- **default mode**: may-write (settings files, only after the user confirms the plan)
- **clients**: Claude Code (CLI, VS Code extension, desktop app); Codex (CLI and app; its VS Code extension on Windows
  runs no hooks while openai/codex#33413 is open — check before relying on it there); Factory Droid; Qwen Code;
  OpenCode; Kilo Code (CLI and VS Code extension) — every component in each; see [Clients](#clients) for the
  clients left out and why
- **customization**: `custom/` holds the setup log, settings backups and runtime state of the project scope; the
  user scope's live in `~/.mem/mem-optimize/`, shared by every project.

## Commands

| Command | What it does |
|---|---|
| `MEM OPTIMIZE SETUP` | Runs the setup wizard: asks which components to enable and where, shows the full plan, writes it after one confirmation. Run again to change the answers |
| `MEM OPTIMIZE STATUS` | Shows what mem-optimize has installed in each settings file: hooks, disabled tools, allow rules; and a shared `handoff.md` left by an earlier version, which is never delivered, so that it can be recovered by hand. Read-only |
| `MEM OPTIMIZE RESET` | Removes everything mem-optimize added, and only that, whichever project's setup added it. Backups of the settings files stay in `~/.mem/mem-optimize/backups/` (user scope) and `custom/backups/` (project scope) |
| `MEM OPTIMIZE PAGES` | Lists the knowledge base pages that weigh most on sessions, with a maintenance suggestion for each. Needs mem-stats; read-only: it never edits a page |

## Components

| Component | What the user sees | Cost |
|---|---|---|
| **Advisor** | Silent below the threshold (default 400k tokens of context). Above it the agent says, once, at a natural breakpoint, that a restart would pay; again past the insist threshold (600k) | One interpreter start per prompt; no tokens below the threshold |
| **Guided restart** | Only after the user agrees, the agent updates the KB's resume point, writes a short handoff note and asks for `/clear`; the fresh session opens by confirming the note was restored | The note, a few thousand characters |
| **Restore after `/clear`** | Every `/clear` (on OpenCode and Kilo, `/new`) carries the conversation over — the snapshot of its last exchanges (prompts, final replies, files changed) is restored in the fresh session, with any handoff note or held message of that chat, and the first reply says what was restored. Claude Code saves it as the chat ends and proves the chat by its client process; the other clients save a checkpoint at the end of every turn and match it by process too, which there may be shared by several chats (then a list). `auto` (default), `offer` (one line, loaded on request) or `off` | The snapshot, at most 6,000 characters, against the whole context `/clear` sheds; on the other clients, a short local write at the end of every turn |
| **Long-pause stop** | After a pause longer than the prompt cache lasts, on a context of 200k+ tokens, the first prompt is stopped once with a message offering (A) `/clear`, the message being carried into the fresh session with a snapshot of the last exchanges, or (B) sending again to continue here. After a compaction (`/compact`, auto-compact) the size is the summary's; a pause Claude Code's idle compaction will handle is left to it (no stop, no advice); `/clear`, `/new` and `/compact` reaching the prompt hook as text are never stopped; Codex signed in with ChatGPT is never stopped (see [Long pause and the client's own cache handling](#long-pause-and-the-clients-own-cache-handling)) | Nothing is sent to the model when stopping |
| **After a compaction** | When the client compacts the conversation, a short pointer tells the agent to re-read the KB index and the latest resume point: the summary stays the reference for the work in progress, the KB for decisions and conventions | A few hundred characters, once per compaction, plus the two re-reads |
| **Unused tools** | Built-in tools the user chooses to disable — `Artifact` always offered, plus those never or rarely called, or heavy — so their definitions leave every request | Takes effect in a new session |

Thresholds are configurable. The advisor and the stop read the session transcript; they send nothing anywhere.

### Long pause and the client's own cache handling

- **Claude Code's idle compaction** (`idleCompaction`, on by default; VS Code and the desktop app since 2.1.314)
  compacts a conversation of 200k+ tokens idle for about an hour on the one-hour cache, so that the next message
  sends a summary. The stop measures the context from the transcript, where a compaction leaves a `compact_boundary`
  with the summary's size (`postTokens`) and no usage of its own: the boundary stands for the last request, so after
  `/compact` or auto-compact a conversation is not stopped, nor advised, on a size it no longer has. Idle compaction
  is different: its summary stays in the client and the boundary is written only after the next prompt has passed
  the prompt hook (observed 2026-10-30), so stopping that prompt would only delay a summary that already makes the
  pause cheap. When its conditions hold, the stop and the advisor stand down for that prompt (log: `decision`
  `idle-compaction`, `idle_compaction` `expected`, or the first condition that failed). Checked from the transcript
  and the settings files: the last request wrote to the one-hour cache; Claude Code 2.1.290 or later, not an SDK or
  `-p` session (the changelog adds VS Code in 2.1.314, but 2.1.310 was seen compacting there); `idleCompaction` and
  `autoCompactEnabled` not `false` in user, project (cwd and its repository), local or managed settings files
  (`CLAUDE_CONFIG_DIR`, or `--claude-home`); `DISABLE_AUTO_COMPACT` and `DISABLE_COMPACT` not set; feature flags
  fetched (`DISABLE_GROWTHBOOK`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`; before 2.1.314 also telemetry off and
  third-party providers); the context at or above `CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS` (200k, floor 100k). Not
  visible to the hook: server-managed and MDM settings, an update during the pause, and a computer asleep before the
  hour was up (no summary then: the rewrite happens unstopped). On the five-minute cache, or with idle compaction
  off, the stop works as before; `"idleCompaction": false` gives the pause back to mem-optimize.
- **Codex signed in with ChatGPT** (`auth_mode` `chatgpt` in `auth.json`, in `CODEX_HOME` or `~/.codex`): OpenAI
  announced in October 2026 that it keeps the conversation's cache indefinitely, so a pause costs no rewrite and the
  stop never applies; the advisor still does. Only `auth_mode` is read, never the tokens. With an API key, or when the
  file is missing (credentials in the system keyring), the 30-minute lifetime applies (`--codex-ttl`). Announced, not
  documented by OpenAI at the time of writing: check again when it is.

## Clients

Every component needs something from the client: the advisor a prompt hook that adds context and the session's
token usage; the stop a prompt hook that blocks with a message; the guided restart a session-start hook that adds
context; compaction support a hook on compaction. **mem-optimize supports a client only when it can carry the advice
to the agent and the stop message to the user**: a client that runs it halfway would leave the user guessing what it
does. Supported clients:

| Client | Settings mem-optimize writes | Advisor | Restart | Stop | Compaction |
|---|---|---|---|---|---|
| Claude Code (CLI, VS Code, desktop app's local sessions) | `~/.claude/settings.json` or `.claude/settings.local.json` | yes | yes | yes | yes |
| Codex | `~/.codex/hooks.json` or `.codex/hooks.json` | yes | yes | yes | yes |
| Factory Droid | `~/.factory/hooks.json`² | yes | yes | yes | yes |
| Qwen Code | `~/.qwen/settings.json`, plus a `Stop` hook that records usage³ | yes | yes | yes | yes |
| OpenCode | `~/.config/opencode/plugins/mem-optimize.js` | yes | yes (`/new`) | yes¹ | yes⁴ |
| Kilo Code (CLI, VS Code) | `~/.config/kilo/plugin/mem-optimize.js` (module descriptor) | yes | yes (`/new`) | yes¹ | yes⁴ |

¹ Thrown from the plugin's `chat.message`, which ends the prompt before it is saved; OpenCode's plugin hooks used
here are partly `experimental`. ² Droid reads `settings.json`'s `hooks` key only while `hooks.json` does not exist: the wizard writes there only when
the user's hooks already live there. ³ Qwen's `Stop` hook receives the last request's `input_tokens`, kept in one file
per session; the prompt hook reads them when the transcript carries no usage. Qwen also runs `UserPromptSubmit` on
tool results and other continuations: only an event with `submitted_prompt` (the user's text, before any command
expansion) is advised, stopped or held, and that text is what gets carried over. ⁴ `experimental.session.compacting` runs before the summary is
written, so the pointer is kept and added, through `experimental.chat.messages.transform`, to the first user message
after the compaction (the automatic continuation or the next prompt), identically in every later request; when the
plugin stops a prompt it shows the reason in a TUI toast, because OpenCode reports a plugin's error only as
"Unexpected server error".

Only Claude Code and Codex take the project scope; the others are configured for all projects. Usage is read from
Claude Code's and Codex's transcripts, from OpenCode's database (`opencode.db`) and Kilo's (found in its data
folder) — or the one `OPENCODE_DB` / `KILO_DB` names in the client's environment, which the plugin resolves as the
client does (absolute as is, relative inside the data folder) — from Qwen's `Stop` hook, and from Droid's and Qwen's transcripts by recognising any common usage shape
(`clients.py`); when none is found the advisor and the stop stay silent.

Not supported, because they cannot carry both messages:

| Client | Missing |
|---|---|
| Cursor | the advice: `beforeSubmitPrompt` can block but not add context; `sessionStart` context reportedly does not always reach the model |
| Antigravity (app, IDE, `agy` CLI) | both: `PreInvocation` cannot block, and its transcript has no token counts (only an undocumented binary format in the conversation's database) |
| GitHub Copilot | the advice: it ignores the output of prompt hooks |
| Windsurf / Devin Desktop | the advice: no context from prompt hooks, no session hook |
| Cline | hooks not available on Windows at launch |

Cursor and Copilot can also run Claude Code's own hooks with payloads of their own: the runners recognise those and
do nothing.

## When executable content is not allowed

Every component is code. When this extension is loaded or invoked, or the user asks to install it, and
`extensions_allow_executable_content` is not `true` in `MEM.config.md` (absent means `false`), the agent **must not**
run any runner and **must**:

1. tell the user that the setting is off, and that MEM therefore forbids running this extension's code;
2. say plainly what follows: **while the setting stays `false`, mem-optimize is installed but does nothing** — no
   advice, no restart carry-over, no stop after a long pause, and the wizard cannot run;
3. ask for authorization to set `extensions_allow_executable_content: true`, naming the runners listed under
   **executable content** as the code that would then run, and noting that the setting covers every installed
   extension declaring executable content;
4. change `MEM.config.md` only after an explicit yes. On a no, run nothing and do not ask again in the session.

## Setup wizard (`MEM OPTIMIZE SETUP`)

Run after installation, and whenever the user wants to change the answers. Ask with the client's question tool
(`AskUserQuestion` in Claude Code; `request_user_input` in Codex, Plan mode only — numbered questions otherwise),
recommended option first, in the user's language. **Explain every question
plainly**: what the option does, what it costs, what changes if refused. Write nothing until the final confirmation.

0. **Executable content** — only if off: as in the section above. Without it the wizard stops.
   **Clients** (multi-select) — Claude Code · Codex · Factory Droid · Qwen Code · OpenCode · Kilo Code, offering
   and pre-selecting those installed (`~/.claude/`, `~/.codex/`, `~/.factory/`, `~/.qwen/`, `~/.config/opencode/` or
   the `opencode` command, `~/.config/kilo/` or the `kilo` command). If the user also works in an unsupported client
   (Cursor, Antigravity, …), say plainly that mem-optimize does nothing there and why, from [Clients](#clients); that
   Codex runs a new or changed hook only after the user approves it with `/hooks` (CLI) or the app's hook
   review; that OpenCode and Kilo load the plugin when they restart; that the clients other than Claude Code and Codex
   are configured for all projects; and that questions 4 and 8 concern Claude Code only. When questions are capped at
   four options, split the clients over two questions.
1. **Advisor** — on at 400k / 600k (recommended) · custom thresholds · off. Explain that it is silent below the
   threshold and what the advice looks like.
2. **Guided restart** — on (recommended) · off. Explain the flow: agreement, handoff note, `/clear`, the confirmation
   in the first reply of the fresh session.
   Then **Restore after `/clear`** — restore automatically
   (recommended) · offer it with one line · off. Explain: at every `/clear` the snapshot of the chat's last exchanges is
   saved and carried into the fresh session, so that `/clear` sheds the cost of the context without losing the thread;
   only the chat that typed `/clear` receives it; a handoff note or held message is always carried over, whatever the
   answer. Answer key `clear_restore` (`mode`, `scope`).
3. **After a long pause** — stop the first prompt and propose `/clear` with the message carried over
   (recommended) · nothing. Explain that the stopped message is not lost, and that sending again continues here.
4. **Unused tools** (multi-select) — the tools the user may disable. Without mem-stats, offer `Artifact` alone. With
   mem-stats, run its Claude Code ingestion and `report`, and read `fixed_overhead`; the options are, ranked by
   definition weight, **all** of:
   - `Artifact`, **always**, whatever its calls: a loaded tool's definition is re-sent with every request whether
     or not it is ever called, and this one is among the largest;
   - every tool in `loaded_never_called`;
   - every tool in `rarely_called` — called at most once per 1,000 requests carrying it;
   - every tool whose `definition_input_share_percent` in `tool_usage` is 1 or more, even when it is called often.

   Do not narrow this list: a heavy tool left out is the costliest omission the question can make. Pre-select a
   tool only when it has no calls, or when its `last_called` is more than 30 days old; never pre-select one called
   in the last 30 days. For each option, say **what the tool does**, its definition weight (`definition_input_share_percent`),
   its calls and `last_called`, and what the user loses by disabling it. Never disable one not selected.

   Always include an explicit **"Disable none"** option, so that keeping every tool takes one click rather than a
   typed answer; it excludes the others. When the client's question tool caps the options per question (four in
   `AskUserQuestion`), split the tools over several questions, heaviest first, each keeping room for that option
   ("none of these").
5. **Scope, one question per enabled element** (advisor, restart, restore after `/clear`, stop, each tool, report
   permissions) — all projects
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
command with `apply`. It backs up each settings file and records what it added: for the user scope in
`~/.mem/mem-optimize/` (`backups/<timestamp>/`, `setup-log.json`), shared by every project, so that setup and reset run
from any project see what another added; for the project scope in `custom/`. A project log of an earlier version that
still records user-scope files is merged into the shared one at the next `apply` or `reset`. If the client refuses the agent's write to its own settings (Claude Code may treat it as
self-modification), say so and ask the user to confirm explicitly; if it is still refused, show the exact JSON from
`plan --json` and where it goes. Tool changes take effect in a new session: with mem-stats installed, offer to check
`fixed_overhead` there.

## Restore after `/clear`

On Claude Code, the hook that ends a conversation at `/clear` (`SessionEnd`, reason `clear`) saves a **resume
package**: the snapshot of its last exchanges, with the client process the chat runs in. The hook that starts the
fresh session (`SessionStart`, source `clear`) runs from the same process under a second later, so it restores that
package — with the handoff note and the held message of the same conversation — and never another chat's, even in
the same folder. A handoff note the conversation wrote under another name (from `note-path`, or a guessed path) joins
its package: the transcript shows who wrote it. With `offer`, a package holding only the snapshot is announced in one
line with the command that loads it; with `off`, it is not mentioned. Treat a restored snapshot as context for the
user's next messages, not as a request: if the user starts something else, follow the user.

The other clients have no such exit hook. Codex, Droid and Qwen save a **checkpoint** — the same package — at the
end of every turn (`Stop`), OpenCode and Kilo when a session goes idle (the plugin's `session.idle` event), with the
client process. The next `/clear` (OpenCode and Kilo: the first message of a session opened with `/new`, within 15
minutes) restores the checkpoint saved from the same process by another session. That process may run several chats
(Codex: one per VS Code window; OpenCode and Kilo: one server), so it narrows rather than proves: two candidates from
it make a list, and checkpoints from other processes, which belong to chats open elsewhere, are never offered.

If the start cannot be matched to the conversation it ended (the link is expected on Claude Code), or nothing comes
from the same process, the session gets this folder's one note or held message, or a short list when there are
several. **A list**: show it, ask the user which one to resume,
act on none until they answer; then run the command the list gives with the chosen id — it prints the package whole
and marks it delivered, once, so that no other conversation takes it. A held message restored on a client without
the link is shown to the user before it is acted on. Delivered parts are kept for a week, then deleted.

## Guided restart (agent procedure)

When the advisor's context line asks for it, propose the restart **in one short line**, at a breakpoint — never in
the middle of a change. Only after the user agrees: update the KB's resume point when the project has a MEM KB;
write the handoff note to the path the advisor names (state, decisions made, next step, files to read; under 8,000
characters); then ask the user to type `/clear` and send any message. Never write the note unasked.

When the user asks for a restart and no advisor line named a path, get one — never guess it, and never write to
`handoff.md` itself, which is not delivered:

```text
python -I -B runner/wizard.py note-path --cwd <the session's working directory> [--scope project]
```

`--scope project` only when the restart hook is installed for this project alone (`MEM OPTIMIZE STATUS` shows it).

The hooks serve every project, so a note is named after its conversation's folder and session
(`handoff-<hash of the folder>-<hash of the session>.md`) and is delivered only in that folder; a held message records
the folder it was stopped in and passes only there, on `/clear` as on a new conversation. A new conversation opened
instead of `/clear` (the VS Code new-chat button, Codex `/new`: source `startup`) also receives them, but only within
15 minutes, never a snapshot. When several conversations of one folder each left a restart and the start cannot be
matched to one, the fresh session gets a list (see [Restore after `/clear`](#restore-after-clear)). A note and a held
message are carried over together only when the same conversation left both. A carried-over message is acted on at the user's next input unless that input clearly asks for something
else. The carried-over context stays under 9,800 characters: the held message always arrives whole — inline, or by
the path of a file to read — then the note, inline or by path, then the snapshot in the room left.
`/clear` stays the recommended way. Clients without `/clear` restart this way only: OpenCode and Kilo with `/new`,
which the advice and the stop message name.

Known limit: the key is the exact working directory. A project opened from a subfolder, or from a parent folder, does
not receive the note written in the other.

## Files

| Path | Content |
|---|---|
| `runner/hook_prompt.py` | Prompt hook (`UserPromptSubmit` and the other clients' equivalents): advisor and long-pause stop |
| `runner/hook_session.py` | Session hooks: at a `/clear`'s end (Claude Code) saves the resume package; at a start (`clear`, `startup`) restores this conversation's package or lists this folder's; after `compact` the re-orientation pointer |
| `runner/resume.py` | Resume packages (gather, link, compose, deliver) and `claim <id>`, which the agent runs to load a listed package |
| `runner/clients.py` | Each client's payload, usage source and answer format; recognises other clients' payloads |
| `runner/opencode-plugin.js` | Template of OpenCode's and Kilo's plugin: the wizard fills in the interpreter, runner arguments and database |
| `runner/wizard.py` | `plan`, `apply`, `reset`, `status`, `note-path` |
| `runner/pages.py` | `MEM OPTIMIZE PAGES`: heavy pages from a mem-stats report, with suggestions |
| `~/.mem/mem-optimize/setup-log.json`, `~/.mem/mem-optimize/backups/` (user scope), `custom/setup-log.json`, `custom/backups/` (project scope) | What setup added, and the settings files as they were |
| `custom/state/` (project scope) or `~/.mem/mem-optimize/state/` (all projects) | Runtime state, one file per session where sessions could collide: resume packages (`packages/`), advisor state (`advisor-state/`), held prompts (`held-prompt-<hash>.json`), handoff notes (`handoff-<folder>-<session>.md`), Qwen's recorded usage (`usage-recorded/`); logs without content, with each entry's working directory. A `handoff.md` or `held-prompt.json` without a hash is an earlier version's: the note is never delivered, the held prompt only in its own folder. Self-ignoring `.gitignore`: never committed |

For all projects, setup copies the runners to `~/.mem/mem-optimize/<version>/runner/`, so the hooks do not depend on
one project's KB.
