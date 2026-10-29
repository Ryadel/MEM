// mem-optimize for OpenCode and Kilo Code. Written by mem-optimize's setup wizard (MEM OPTIMIZE SETUP) into
// ~/.config/opencode/plugins/mem-optimize.js, or ~/.config/kilo/plugin/mem-optimize.js as a module descriptor (Kilo,
// an OpenCode fork, for its CLI and VS Code extension); MEM OPTIMIZE RESET removes it. Edit the answers, not this file.
//
// These clients have no command hooks: this plugin forwards their events to mem-optimize's Python runners, with the
// Claude-style payload the other clients send, plus the client's database (Kilo: its data folder), where the runners
// read the session's token usage and recent turns. The database is resolved here, in the client's process, as the
// client resolves it: OPENCODE_DB or KILO_DB (CONFIG.dbEnv) when set — absolute or ":memory:" as is, relative inside
// the data folder — otherwise the setup's default.
//
//   chat.message                         -> hook_session.py on a session's first message here (carry-over after
//                                           /new), then hook_prompt.py (advisor, long-pause stop)
//   experimental.session.compacting      -> hook_session.py --compact: the pointer to re-orient from the knowledge
//                                           base, kept for the continuation (this hook runs before the summary is
//                                           written, so text added here would reach the summarizer, not the agent)
//   experimental.chat.messages.transform -> adds that pointer to the first user message after the compaction (the
//                                           automatic "continue" or the user's next prompt), in every later request
//   event session.idle                   -> hook_session.py with a Stop event: a checkpoint of the session's last
//                                           exchanges, which the next session's first message (/new) can restore
//
// Context for the model is appended to the user's message as a synthetic text part, as OpenCode does for files it
// reads: the request's prefix, and so the prompt cache, is untouched. The compaction pointer is not saved: it is
// added again, to the same message, in every request of the process, so the prefix stays the same from one request
// to the next. A long-pause stop is thrown, which ends the prompt before it is saved or sent; OpenCode shows a
// plugin's thrown error only as "Unexpected server error", so the reason is shown first as a TUI toast (the plugin's
// client is SDK v1: arguments under "body"). Any other failure is swallowed and the prompt goes through unchanged.
import { spawn } from "node:child_process"
import { isAbsolute, join } from "node:path"

const CONFIG = /* CONFIG */ null
const TIMEOUT = 20000
const TOAST = 60000 // the stop message is long: a minute to read it

function database() {
  const named = CONFIG.dbEnv ? process.env[CONFIG.dbEnv] : ""
  if (!named) return CONFIG.db
  return named === ":memory:" || isAbsolute(named) ? named : join(CONFIG.data, named)
}

function run(args, event) {
  return new Promise((resolve) => {
    if (!CONFIG || !args) return resolve(null)
    let child
    try {
      // windowsHide: no console window, whatever starts OpenCode (MEM: no visible windows)
      child = spawn(CONFIG.python, ["-I", "-B", ...args], { windowsHide: true, stdio: ["pipe", "pipe", "ignore"] })
    } catch {
      return resolve(null)
    }
    let out = ""
    const timer = setTimeout(() => {
      child.kill()
      resolve(null)
    }, TIMEOUT)
    child.stdout.on("data", (chunk) => {
      out += chunk
    })
    child.on("error", () => {
      clearTimeout(timer)
      resolve(null)
    })
    child.on("close", () => {
      clearTimeout(timer)
      try {
        resolve(out.trim() ? JSON.parse(out) : null)
      } catch {
        resolve(null)
      }
    })
    child.stdin.on("error", () => {})
    child.stdin.end(JSON.stringify({ ...event, opencode_db: database() }))
  })
}

let counter = 0
const LETTERS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

// OpenCode's ids sort by creation: "prt_", 12 hex digits of (milliseconds * 4096 + a counter) on 48 bits, then 14
// random characters.
function partID() {
  const stamp = (BigInt(Date.now()) * 4096n + BigInt(counter++ % 4096)) & 0xffffffffffffn
  const time = stamp.toString(16).padStart(12, "0")
  let random = ""
  for (let i = 0; i < 14; i++) random += LETTERS[Math.floor(Math.random() * LETTERS.length)]
  return "prt_" + time + random
}

function context(answer) {
  return answer?.hookSpecificOutput?.additionalContext || null
}

async function toast(client, message) {
  try {
    await client?.tui?.showToast({ body: { title: "mem-optimize", message, variant: "warning", duration: TOAST } })
  } catch {}
}

export const MemOptimize = async ({ client, directory }) => {
  const seen = new Set() // sessions whose first message here was checked for a carry-over
  const pointers = new Map() // session -> { at, text, messageID, partID }: the latest compaction's pointer
  return {
    "chat.message": async (input, output) => {
      if (!CONFIG) return
      const sessionID = input.sessionID
      const texts = []
      if (CONFIG.session && !seen.has(sessionID)) {
        seen.add(sessionID)
        // The runner tells a new session (no messages yet) from one resumed with --continue.
        const answer = await run(CONFIG.session, {
          hook_event_name: "SessionStart", source: "startup", session_id: sessionID, cwd: directory,
        })
        if (context(answer)) texts.push(context(answer))
      }
      if (CONFIG.prompt) {
        const prompt = (output.parts || [])
          .filter((part) => part.type === "text" && !part.synthetic)
          .map((part) => part.text || "")
          .join("\n")
        const answer = await run(CONFIG.prompt, {
          hook_event_name: "UserPromptSubmit", session_id: sessionID, prompt, cwd: directory,
        })
        if (answer?.decision === "block" && answer.reason) {
          await toast(client, answer.reason)
          throw new Error(answer.reason)
        }
        if (context(answer)) texts.push(context(answer))
      }
      if (!Array.isArray(output.parts)) return
      const messageID = output.message?.id ?? input.messageID
      for (const text of texts) {
        output.parts.push({ id: partID(), sessionID, messageID, type: "text", synthetic: true, text })
      }
    },
    "experimental.session.compacting": async (input) => {
      if (!CONFIG?.compact) return
      const at = Date.now() // before the summary request: only messages created after this are the continuation
      const answer = await run(CONFIG.compact, {
        hook_event_name: "SessionStart", source: "compact", session_id: input.sessionID, cwd: directory,
      })
      if (context(answer)) pointers.set(input.sessionID, { at, text: context(answer), messageID: null, partID: null })
    },
    event: async ({ event }) => {
      // a turn has finished: save the checkpoint the next session (/new) may restore
      if (!CONFIG?.checkpoint || event?.type !== "session.idle") return
      const sessionID = event.properties?.sessionID
      if (sessionID) await run(CONFIG.checkpoint, { hook_event_name: "Stop", session_id: sessionID, cwd: directory })
    },
    "experimental.chat.messages.transform": async (input, output) => {
      const messages = output?.messages
      if (!Array.isArray(messages) || !messages.length) return
      const sessionID = messages[messages.length - 1]?.info?.sessionID
      const pointer = pointers.get(sessionID)
      if (!pointer) return
      if (!pointer.messageID) {
        // The summary request sees only older messages, so it finds nothing here and stays untouched.
        const first = messages.find((message) => message.info?.role === "user"
          && (message.info?.time?.created ?? 0) >= pointer.at
          && !(message.parts || []).some((part) => part.type === "compaction"))
        if (!first) return
        pointer.messageID = first.info.id
        pointer.partID = partID()
      }
      const target = messages.find((message) => message.info?.id === pointer.messageID)
      if (!target || !Array.isArray(target.parts) || target.parts.some((part) => part.id === pointer.partID)) return
      target.parts.push({ id: pointer.partID, sessionID, messageID: pointer.messageID, type: "text", synthetic: true,
        text: pointer.text })
    },
  }
}
