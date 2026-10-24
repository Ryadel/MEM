"""mem-optimize setup for Claude Code, Codex and the other clients in clients.py: turn the wizard's answers into
settings changes, apply them, undo them.

  plan    --answers FILE   show every file and key the answers would change; writes nothing
  apply   --answers FILE   back up each settings file, then write exactly what `plan` shows
  reset                    remove what mem-optimize added (its hooks, the tools it disabled, its allow rules)
  status                   show what mem-optimize currently has in each settings file

Clients (`clients` in the answers; default Claude Code): Claude Code reads ~/.claude/settings.json (scope `user`,
every project) or <workspace>/.claude/settings.local.json (scope `project`); Codex reads ~/.codex/hooks.json or
<workspace>/.codex/hooks.json, with the same hook structure and output, runs a changed hook only after the user
trusts it (/hooks), and has no permissions.deny/allow, so tool and report answers apply to Claude Code only. A client
not chosen loses mem-optimize's earlier entries. Hook entries are recognised by the runner names below, so `apply` replaces
them instead of adding duplicates, and other tools' hooks are never touched. For the user scope the runners are
copied to ~/.mem/mem-optimize/<version>/runner, so the hooks do not depend on one project's KB. State (held prompt,
handoff note, logs) lives in ~/.mem/mem-optimize/state, or in the extension's custom/state for the project scope,
which carries a self-ignoring .gitignore: it holds the user's own words and must never be committed.

The other clients take the user scope only: Factory Droid (~/.factory/hooks.json, Claude Code's event map at the top
level; settings.json's "hooks" key instead only when it already holds the user's hooks and hooks.json does not exist,
since Droid then reads settings.json), Qwen Code (~/.qwen/settings.json, Claude Code's format, plus a Stop hook
recording the last request's input tokens), OpenCode (a plugin, ~/.config/opencode/plugins/mem-optimize.js, written
from runner/opencode-plugin.js) and Kilo Code (the same plugin as a module descriptor, ~/.config/kilo/plugin/, for its
CLI and VS Code extension). Only clients that can carry every component are supported: the advice to the agent and
the stop message to the user (Cursor and Antigravity cannot, see index.md).

Answers (JSON):
  {"clients": ["claude", "codex", "droid", "qwen", "opencode", "kilo"], "lang": "it",
   "cost": "api" | "tokens",
   "advisor": {"enabled": true, "advise": 400000, "insist": 600000, "scope": "user"},
   "restart": {"enabled": true, "scope": "user"},
   "pause_stop": {"enabled": true, "scope": "user"},
   "compaction": {"enabled": true, "scope": "user"},
   "deny_tools": [{"tool": "Artifact", "scope": "user"}],
   "report_permissions": {"enabled": true, "scope": "user"}}

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

RUNNERS = ("hook_prompt.py", "hook_session.py", "clients.py", "wizard.py", "opencode-plugin.js")
# Earlier runner names too, so that apply replaces hooks installed before the rename.
MARK = re.compile(r"mem-optimize.*/(hook_prompt|hook_session|claude_advisor|claude_session)\.py")
SCOPES = ("user", "project")
CLIENTS = ("claude", "codex", "droid", "qwen", "opencode", "kilo")
CLAUDE_STYLE = ("claude", "codex", "droid", "qwen")  # Claude Code's settings format
QUOTED = ("claude", "codex", "droid")  # shells known to read Claude Code's quoted command lines
OPENCODE_FAMILY = ("opencode", "kilo")  # a plugin file instead of settings
PROJECT_SCOPE = ("claude", "codex")  # the other clients' project files are usually committed: user scope only
CLIENT_NAMES = {"claude": "Claude Code", "codex": "Codex", "droid": "Factory Droid", "opencode": "OpenCode",
                "qwen": "Qwen Code", "kilo": "Kilo Code"}
COMPONENTS = ("advisor", "restart", "pause_stop", "compaction")
# How the user starts a fresh session, where it is not /clear.
RESTART = {"opencode": "/new", "kilo": "/new"}
LABELS = {
    "claude": {"UserPromptSubmit": "UserPromptSubmit", "SessionStart": "SessionStart (clear, startup)",
               "SessionStartCompact": "SessionStart (compact)"},
    "opencode": {"UserPromptSubmit": "chat.message", "SessionStart": "chat.message, first of a session",
                 "SessionStartCompact": "experimental.session.compacting, then the next user message"},
}
LABELS["kilo"] = LABELS["opencode"]
NOTES = {
    "codex": "then approve the new hooks in Codex: /hooks in the CLI, or the app's hook review (Codex runs a changed "
             "hook only once it is trusted)",
    "opencode": "uses OpenCode's plugin hooks, some of them experimental; takes effect when OpenCode restarts",
    "kilo": "the same plugin as OpenCode's, for Kilo's CLI and VS Code extension; takes effect when Kilo restarts",
    "qwen": "the Stop hook records each request's input tokens, which the advisor and the stop read",
}
SAFE = re.compile(r"^[\w./:\\=+@,-]+$")


def posix(path):
    return Path(path).resolve().as_posix()


def quoted(path):
    return '"' + posix(path) + '"'  # Claude Code runs hooks through a shell: forward slashes, quoted


def empty():
    return {"UserPromptSubmit": [], "SessionStart": [], "SessionStartCompact": [], "Stop": [], "deny": [], "allow": []}


class Layout:
    def __init__(self, args):
        self.home, self.extension = Path(args.home).expanduser(), Path(args.extension_dir)
        self.workspace, self.kb_root, self.python = args.workspace, args.kb_root, args.python
        self.stats_db, self.prices = args.stats_db, args.prices
        self.clients = (args.client,) if args.client else CLIENTS
        self.real_home = args.home == "~"
        self.version = re.search(r"\*\*version\*\*:\s*(\S+)",
                                 (self.extension / "index.md").read_text(encoding="utf-8")).group(1)

    def xdg(self, variable, default):
        """XDG folders, honoured for the real home only (tests pass their own)."""
        value = os.environ.get(variable) if self.real_home else None
        return Path(value) if value else self.home / default

    def settings(self, scope, client="claude"):
        if scope == "user":
            return {"codex": self.home / ".codex" / "hooks.json",
                    "droid": self.droid(),
                    "qwen": self.home / ".qwen" / "settings.json",
                    "opencode": self.xdg("XDG_CONFIG_HOME", ".config") / "opencode" / "plugins" / "mem-optimize.js",
                    "kilo": self.xdg("XDG_CONFIG_HOME", ".config") / "kilo" / "plugin" / "mem-optimize.js",
                    }.get(client, self.home / ".claude" / "settings.json")
        if client not in PROJECT_SCOPE:
            raise SystemExit(CLIENT_NAMES[client] + " takes the user scope only")
        if self.workspace is None:
            raise SystemExit("the project scope needs --workspace")
        if client == "codex":
            return Path(self.workspace) / ".codex" / "hooks.json"
        return Path(self.workspace) / ".claude" / "settings.local.json"

    def droid(self):
        """The file Droid reads: ~/.factory/hooks.json (events at the top level); settings.json's "hooks" key only
        while hooks.json does not exist, so that one is used only when it already holds the user's hooks."""
        hooks, settings = self.home / ".factory" / "hooks.json", self.home / ".factory" / "settings.json"
        if not hooks.exists() and "hooks" in load(settings):
            return settings
        return hooks

    def data(self, client):
        """OpenCode's or Kilo's data folder."""
        return self.xdg("XDG_DATA_HOME", ".local/share") / client

    def database(self, client):
        """OpenCode's default database; for Kilo, its data folder: the runner finds the database in it (name
        undocumented). The plugin prefers OPENCODE_DB or KILO_DB when the client runs with one set."""
        if client == "kilo":
            return self.data(client)
        return self.data(client) / "opencode.db"

    def runner(self, scope):
        if scope == "user":
            return self.home / ".mem" / "mem-optimize" / self.version / "runner"
        return self.extension / "runner"

    def state(self, scope):
        if scope == "user":
            return self.home / ".mem" / "mem-optimize" / "state"
        return self.extension / "custom" / "state"


def command(layout, scope, script, *options):
    parts = [quoted(layout.python), "-I", "-B", quoted(layout.runner(scope) / script)]
    for option in options:
        parts.append(quoted(option) if isinstance(option, Path) else str(option))
    return " ".join(parts)


def portable(layout, scope, script, *options):
    """A command line for clients whose shell is not documented (Qwen): bare words when no part needs quoting, which
    every shell reads alike; otherwise quoted."""
    parts = [posix(layout.python), "-I", "-B", posix(layout.runner(scope) / script)]
    parts += [posix(o) if isinstance(o, Path) else str(o) for o in options]
    return " ".join(p if SAFE.match(p) else '"' + p + '"' for p in parts)


def argv(layout, scope, script, *options):
    """OpenCode's plugin spawns the runner without a shell: the arguments after the interpreter's own."""
    return [posix(layout.runner(scope) / script)] + [posix(o) if isinstance(o, Path) else str(o) for o in options]


def render(layout, scope, script, client, options):
    if client in QUOTED:
        return command(layout, scope, script, *options)
    if client in OPENCODE_FAMILY:
        return argv(layout, scope, script, *options)
    return portable(layout, scope, script, *options)


def wanted(answers, layout, client="claude"):
    """Per scope: the hook commands, denied tools and allow rules the answers ask for, for one client."""
    result = {scope: empty() for scope in SCOPES}
    advisor, restart, pause, compaction = (answers.get(k) or {} for k in COMPONENTS)
    named = [] if client in PROJECT_SCOPE else ["--client", client]  # Claude Code and Codex: the default
    restarts = ["--restart", RESTART[client]] if client in RESTART else []
    lang = answers.get("lang") or "en"
    prices = layout.prices if answers.get("cost", "api") == "api" and layout.prices else None
    for scope in SCOPES:
        if scope == "project" and client not in PROJECT_SCOPE:
            continue
        state = layout.state(scope)
        advise = advisor.get("enabled") and advisor.get("scope", "user") == scope
        stop = pause.get("enabled") and pause.get("scope", "user") == scope
        handoff = restart.get("enabled") and restart.get("scope", "user") == scope
        if advise or stop:
            options = ["--state", state / "advisor-state.json"]
            if prices:
                options += ["--prices", layout.runner(scope) / prices.name]
            if advise:
                options += ["--advise", int(advisor.get("advise") or 400_000),
                            "--insist", int(advisor.get("insist") or 600_000)]
                if restart.get("enabled") and (client in PROJECT_SCOPE or restart.get("scope", "user") == "user"):
                    options += ["--handoff", layout.state(restart.get("scope", "user")) / "handoff.md"]
            else:
                options.append("--no-advice")
            if stop:
                options += ["--pause-stop", "--held", state / "held-prompt.json"]
                if pause.get("min_tokens"):
                    options += ["--pause-min", int(pause["min_tokens"])]
                if pause.get("test_after_seconds"):  # live tests only: a pause this long counts as expired cache
                    options += ["--pause-after", int(pause["test_after_seconds"])]
            options += ["--lang", lang, "--log", state / "hook-prompt.jsonl"] + named + restarts
            result[scope]["UserPromptSubmit"].append(render(layout, scope, "hook_prompt.py", client, options))
            if client == "qwen":  # Qwen's Stop hook carries the request's input tokens: recorded for the prompt hook
                options = ["--state", state / "advisor-state.json", "--log", state / "hook-prompt.jsonl"] + named
                result[scope]["Stop"].append(render(layout, scope, "hook_prompt.py", client, options))
        if handoff or stop:
            options = []
            if handoff:
                options += ["--handoff", state / "handoff.md"]
            if stop:
                options += ["--held", state / "held-prompt.json"]
            if scope == "project" and layout.kb_root is not None:
                options += ["--kb-root", Path(layout.kb_root)]
            options += ["--log", state / "hook-session.jsonl"] + named
            result[scope]["SessionStart"].append(render(layout, scope, "hook_session.py", client, options))
        if compaction.get("enabled") and compaction.get("scope", "user") == scope:
            options = ["--compact"]
            if scope == "project" and layout.kb_root is not None:
                options += ["--kb-root", Path(layout.kb_root)]
            options += ["--log", state / "hook-session.jsonl"] + named
            result[scope]["SessionStartCompact"].append(render(layout, scope, "hook_session.py", client, options))
    if client != "claude":  # permissions.deny/allow are Claude Code's
        return result
    for item in answers.get("deny_tools") or []:
        bucket = result[item.get("scope", "user")]["deny"]
        if item["tool"] not in bucket:
            bucket.append(item["tool"])
    reports = answers.get("report_permissions") or {}
    if reports.get("enabled"):
        scope = reports.get("scope", "user")
        rules = result[scope]["allow"]
        rules.append("Bash(" + command(layout, scope, "wizard.py") + " status*)")
        if layout.stats_db is not None:
            stats = Path(layout.extension).parent / "mem-stats" / "runner" / "stats.py"
            rules.append("Bash(" + " ".join([quoted(layout.python), "-I", "-B", quoted(stats), "--db",
                                             quoted(layout.stats_db)]) + " report*)")
    return result


def bare(client, path):
    """Files that hold the event map itself, not a "hooks" key: Droid's hooks.json."""
    return client == "droid" and path.name == "hooks.json"


def load(path, client="claude"):
    if client in OPENCODE_FAMILY:
        try:
            return {"plugin": path.read_text(encoding="utf-8")}
        except FileNotFoundError:
            return {}
    try:
        settings = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    return {"hooks": settings} if bare(client, path) and settings else settings


def ours(hook):
    return bool(MARK.search(hook.get("command") or ""))


def strip(settings, recorded):
    """settings without mem-optimize's hooks and without the deny/allow entries it recorded as added. Commands are
    removed one by one: a group keeps any other tool's command, and goes only when nothing is left in it."""
    hooks = settings.get("hooks") or {}
    for event in list(hooks):
        groups = []
        for group in hooks[event]:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                groups.append(group)
                continue
            kept = [h for h in group["hooks"] if not (isinstance(h, dict) and ours(h))]
            if kept:
                groups.append({**group, "hooks": kept})
        hooks[event] = groups
        if not hooks[event]:
            del hooks[event]
    if "hooks" in settings and not hooks:
        del settings["hooks"]
    permissions = settings.get("permissions") or {}
    for key in ("deny", "allow"):
        if key in permissions:
            permissions[key] = [r for r in permissions[key] if r not in recorded.get(key, [])]
            if not permissions[key]:
                del permissions[key]
    if "permissions" in settings and not permissions:
        del settings["permissions"]
    return settings


def merged(settings, want, recorded):
    """settings with exactly `want` from mem-optimize; returns (settings, entries it added to deny/allow)."""
    settings = strip(json.loads(json.dumps(settings)), recorded)
    hooks = settings.setdefault("hooks", {})
    # The restart hook runs on /clear and on a new conversation (startup); it decides itself whether a note is ours.
    for key, event, matcher in (("UserPromptSubmit", "UserPromptSubmit", None), ("SessionStart", "SessionStart", "clear"),
                                ("SessionStart", "SessionStart", "startup"),
                                ("SessionStartCompact", "SessionStart", "compact"), ("Stop", "Stop", None)):
        for line in want[key]:
            group = {"hooks": [{"type": "command", "command": line}]}
            if matcher:
                group = {"matcher": matcher, **group}
            hooks.setdefault(event, []).append(group)
    if not hooks:
        del settings["hooks"]
    added = {}
    for key in ("deny", "allow"):
        if want[key]:
            rules = settings.setdefault("permissions", {}).setdefault(key, [])
            added[key] = [r for r in want[key] if r not in rules]
            rules.extend(added[key])
    return settings, added


def plugin(layout, want, client="opencode"):
    """OpenCode's or Kilo's plugin: the template with this setup's interpreter, runner arguments and database. Kilo
    loads a plugin from its default export, a module descriptor {id, server}."""
    config = {"python": posix(layout.python), "db": posix(layout.database(client)), "data": posix(layout.data(client)),
              "dbEnv": client.upper() + "_DB",
              "prompt": (want["UserPromptSubmit"] or [None])[0], "session": (want["SessionStart"] or [None])[0],
              "compact": (want["SessionStartCompact"] or [None])[0]}
    template = (layout.extension / "runner" / "opencode-plugin.js").read_text(encoding="utf-8")
    text = template.replace("/* CONFIG */ null", json.dumps(config, indent=2))
    if client == "kilo":
        text = text.replace("export const MemOptimize = ", "const MemOptimize = ", 1)
        text += '\nexport default { id: "mem-optimize", server: MemOptimize }\n'
    return text


def merged_for(client, layout, settings, want, recorded):
    if client in CLAUDE_STYLE:
        return merged(settings, want, recorded)
    hooks = any(want[k] for k in ("UserPromptSubmit", "SessionStart", "SessionStartCompact"))
    return ({"plugin": plugin(layout, want, client)} if hooks else {}), {}


def hooks_in(client, settings):
    """mem-optimize's hook commands in one client's settings."""
    if client in CLAUDE_STYLE:
        return [h.get("command") for groups in (settings.get("hooks") or {}).values() for g in groups
                if isinstance(g, dict) for h in g.get("hooks") or [] if isinstance(h, dict) and ours(h)]
    return ["plugin"] if settings.get("plugin") else []


def setup_log(layout):
    return layout.extension / "custom" / "setup-log.json"


def read_log(layout):
    log = load(setup_log(layout))
    return log if isinstance(log, dict) else {}


def targets(layout, scopes=SCOPES):
    """(client, scope, settings path) for every place mem-optimize may write; scopes it cannot locate are skipped."""
    for client in layout.clients:
        for scope in scopes:
            try:
                yield client, scope, layout.settings(scope, client)
            except SystemExit:
                continue


def plan(layout, answers):
    log = read_log(layout)
    clients = answers.get("clients") or ["claude"]
    wants = {client: wanted(answers, layout, client) for client in CLIENTS}
    changes = []
    for client, scope, path in targets(layout):
        # A client not chosen gets nothing: its earlier mem-optimize entries are removed.
        mine = wants[client][scope] if client in clients else empty()
        before = load(path, client)
        after, added = merged_for(client, layout, before, mine, log.get(posix(path), {}))
        if after != before:
            changes.append({"client": client, "scope": scope, "file": posix(path), "before": before, "after": after,
                            "added": added, "want": mine})
    copies = []
    if any(wants[c]["user"][k] for c in clients if c in wants
           for k in ("UserPromptSubmit", "SessionStart", "SessionStartCompact", "allow")):
        target = layout.runner("user")
        copies = [(layout.extension / "runner" / name, target / name) for name in RUNNERS
                  if (layout.extension / "runner" / name).is_file()]
        if layout.prices and answers.get("cost", "api") == "api":
            copies.append((layout.prices, target / layout.prices.name))
    return changes, copies, wants


def describe(changes, copies, wants):
    lines = []
    for change in changes:
        client = change["client"]
        lines.append("%s, %s scope: %s" % (CLIENT_NAMES[client], change["scope"], change["file"]))
        mine, labels = change["want"], LABELS.get(client, LABELS["claude"])
        for event in ("UserPromptSubmit", "SessionStart", "SessionStartCompact"):
            for line in mine[event]:
                shown = " ".join(line) if isinstance(line, list) else line
                lines.append("  hook %s: %s" % (labels[event], shown))
        for rule in mine["deny"]:
            lines.append("  permissions.deny: %s (the tool leaves Claude's context; takes effect in a new session)"
                         % rule)
        for rule in mine["allow"]:
            lines.append("  permissions.allow: %s" % rule)
        if not any(mine.values()):
            lines.append("  remove mem-optimize's entries")
            continue
        if client in OPENCODE_FAMILY:
            lines.append("  write the plugin file with these runner calls")
        if client in NOTES:
            lines.append("  " + NOTES[client])
        if client == "codex" and change["scope"] == "project":
            lines.append("  project hooks load only if Codex trusts this project")
    for source, target in copies:
        lines.append("copy %s -> %s" % (posix(source), posix(target)))
    return "\n".join(lines) or "nothing to change"


def write(path, client, settings):
    """Write one client's settings atomically; OpenCode's and Kilo's plugin is a file of its own, deleted when
    empty."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if client in OPENCODE_FAMILY:
        if not settings.get("plugin"):
            path.unlink(missing_ok=True)
            return
        text = settings["plugin"]
    else:
        content = (settings.get("hooks") or {}) if bare(client, path) else settings
        text = json.dumps(content, indent=2, ensure_ascii=False) + "\n"
    temporary = path.with_name(path.name + ".mem-optimize.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def apply(layout, answers):
    changes, copies, _ = plan(layout, answers)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backups = layout.extension / "custom" / "backups" / stamp
    log = read_log(layout)
    for source, target in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for scope in SCOPES:
        state = layout.state(scope)
        state.mkdir(parents=True, exist_ok=True)
        if scope == "project":
            (state / ".gitignore").write_text("*\n", encoding="utf-8")
    for change in changes:
        path = Path(change["file"])
        backup = backups / (change["client"] + "-" + change["scope"] + "-" + path.name)
        existed = path.exists()
        if existed:
            backups.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
        write(path, change["client"], change["after"])
        previous = log.get(change["file"], {})
        log[change["file"]] = {key: sorted(set(previous.get(key, [])) | set(change["added"].get(key, [])))
                               for key in ("deny", "allow")}
        log[change["file"]].update(backup=posix(backup) if existed else None, applied=stamp)
    setup_log(layout).parent.mkdir(parents=True, exist_ok=True)
    setup_log(layout).write_text(json.dumps(log, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return changes


def reset(layout):
    log, changed = read_log(layout), []
    for client, _, path in targets(layout):
        before = load(path, client)
        if client in CLAUDE_STYLE:
            after = strip(json.loads(json.dumps(before)), log.get(posix(path), {}))
        else:
            after, _ = merged_for(client, layout, before, empty(), {})
        if after != before:
            write(path, client, after)
            changed.append(posix(path))
        log.pop(posix(path), None)
    if setup_log(layout).exists():
        setup_log(layout).write_text(json.dumps(log, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return changed


def status(layout):
    log, report = read_log(layout), {}
    for client, scope, path in targets(layout):
        settings, recorded = load(path, client), log.get(posix(path), {})
        permissions = settings.get("permissions") or {}
        report[client + ":" + scope] = {
            "file": posix(path), "hooks": hooks_in(client, settings),
            "denied_tools": [r for r in permissions.get("deny", []) if r in recorded.get("deny", [])],
            "allow_rules": [r for r in permissions.get("allow", []) if r in recorded.get("allow", [])]}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("plan", "apply", "reset", "status"))
    parser.add_argument("--answers", type=Path, help="the wizard's answers (plan, apply)")
    parser.add_argument("--extension-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--workspace", type=Path, help="project folder whose .claude/ receives project-scope settings")
    parser.add_argument("--kb-root", type=Path, help="the project's MEM KB, named in the carry-over after /clear")
    parser.add_argument("--home", default="~", help="user home (tests)")
    parser.add_argument("--python", default=sys.executable, help="interpreter the hooks run with")
    parser.add_argument("--prices", type=Path, help="mem-stats price card, for API-equivalent costs in advice")
    parser.add_argument("--stats-db", type=Path, help="mem-stats ledger, for the report allow rule")
    parser.add_argument("--client", choices=CLIENTS, help="touch only this client's files (default: all)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()
    layout = Layout(args)
    if args.action in ("plan", "apply"):
        if args.answers is None:
            parser.error(args.action + " needs --answers")
        answers = json.loads(args.answers.read_text(encoding="utf-8-sig"))
        unknown = [c for c in answers.get("clients") or [] if c not in CLIENTS]
        if unknown:
            parser.error("unknown clients: " + ", ".join(unknown))
        if args.action == "plan":
            changes, copies, want = plan(layout, answers)
            output = ({"changes": changes, "copies": [[posix(s), posix(t)] for s, t in copies]} if args.json
                      else describe(changes, copies, want))
        else:
            output = {"applied": [c["file"] for c in apply(layout, answers)]}
    elif args.action == "reset":
        output = {"reset": reset(layout)}
    else:
        output = status(layout)
    sys.stdout.write((output if isinstance(output, str) else json.dumps(output, indent=2, ensure_ascii=False)) + "\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
