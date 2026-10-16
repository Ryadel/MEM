"""mem-optimize setup for Claude Code and Codex: turn the wizard's answers into settings changes, apply them, undo
them.

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

Answers (JSON):
  {"clients": ["claude", "codex"], "lang": "it", "cost": "api" | "tokens",
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
import re
import shutil
import sys
import time
from pathlib import Path

RUNNERS = ("hook_prompt.py", "hook_session.py", "wizard.py")
# Earlier runner names too, so that apply replaces hooks installed before the rename.
MARK = re.compile(r"mem-optimize.*/(hook_prompt|hook_session|claude_advisor|claude_session)\.py")
SCOPES = ("user", "project")
CLIENTS = ("claude", "codex")
CLIENT_NAMES = {"claude": "Claude Code", "codex": "Codex"}


def posix(path):
    return Path(path).resolve().as_posix()


def quoted(path):
    return '"' + posix(path) + '"'  # Claude Code runs hooks through a shell: forward slashes, quoted


class Layout:
    def __init__(self, args):
        self.home, self.extension = Path(args.home).expanduser(), Path(args.extension_dir)
        self.workspace, self.kb_root, self.python = args.workspace, args.kb_root, args.python
        self.stats_db, self.prices = args.stats_db, args.prices
        self.clients = (args.client,) if args.client else CLIENTS
        self.version = re.search(r"\*\*version\*\*:\s*(\S+)",
                                 (self.extension / "index.md").read_text(encoding="utf-8")).group(1)

    def settings(self, scope, client="claude"):
        if scope == "user":
            return self.home / ".codex" / "hooks.json" if client == "codex" else self.home / ".claude" / "settings.json"
        if self.workspace is None:
            raise SystemExit("the project scope needs --workspace")
        if client == "codex":
            return Path(self.workspace) / ".codex" / "hooks.json"
        return Path(self.workspace) / ".claude" / "settings.local.json"

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


def wanted(answers, layout):
    """Per scope: the hook commands, denied tools and allow rules the answers ask for."""
    result = {scope: {"UserPromptSubmit": [], "SessionStart": [], "SessionStartCompact": [], "deny": [], "allow": []}
              for scope in SCOPES}
    advisor, restart, pause, compaction = (answers.get(k) or {} for k in ("advisor", "restart", "pause_stop",
                                                                          "compaction"))
    lang = answers.get("lang") or "en"
    prices = layout.prices if answers.get("cost", "api") == "api" and layout.prices else None
    for scope in SCOPES:
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
                if restart.get("enabled"):
                    options += ["--handoff", layout.state(restart.get("scope", "user")) / "handoff.md"]
            else:
                options.append("--no-advice")
            if stop:
                options += ["--pause-stop", "--held", state / "held-prompt.json"]
                if pause.get("min_tokens"):
                    options += ["--pause-min", int(pause["min_tokens"])]
                if pause.get("test_after_seconds"):  # live tests only: a pause this long counts as expired cache
                    options += ["--pause-after", int(pause["test_after_seconds"])]
            options += ["--lang", lang, "--log", state / "hook-prompt.jsonl"]
            result[scope]["UserPromptSubmit"].append(command(layout, scope, "hook_prompt.py", *options))
        if handoff or stop:
            options = []
            if handoff:
                options += ["--handoff", state / "handoff.md"]
            if stop:
                options += ["--held", state / "held-prompt.json"]
            if scope == "project" and layout.kb_root is not None:
                options += ["--kb-root", Path(layout.kb_root)]
            options += ["--log", state / "hook-session.jsonl"]
            result[scope]["SessionStart"].append(command(layout, scope, "hook_session.py", *options))
        if compaction.get("enabled") and compaction.get("scope", "user") == scope:
            options = ["--compact"]
            if scope == "project" and layout.kb_root is not None:
                options += ["--kb-root", Path(layout.kb_root)]
            options += ["--log", state / "hook-session.jsonl"]
            result[scope]["SessionStartCompact"].append(command(layout, scope, "hook_session.py", *options))
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


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}


def ours(group):
    return any(MARK.search(h.get("command") or "") for h in group.get("hooks") or [])


def strip(settings, recorded):
    """settings without mem-optimize's hooks and without the deny/allow entries it recorded as added."""
    hooks = settings.get("hooks") or {}
    for event in list(hooks):
        hooks[event] = [g for g in hooks[event] if not ours(g)]
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
                                ("SessionStartCompact", "SessionStart", "compact")):
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
    want, log = wanted(answers, layout), read_log(layout)
    clients = answers.get("clients") or ["claude"]
    changes = []
    for client, scope, path in targets(layout):
        # A client not chosen gets nothing: its earlier mem-optimize entries are removed.
        mine = want[scope] if client in clients else {k: [] for k in want[scope]}
        if client == "codex":  # no permissions.deny/allow in Codex; tools stay as they are there
            mine = {**mine, "deny": [], "allow": []}
        before = load(path)
        after, added = merged(before, mine, log.get(posix(path), {}))
        if after != before:
            changes.append({"client": client, "scope": scope, "file": posix(path), "before": before, "after": after,
                            "added": added, "want": mine})
    copies = []
    if any(want["user"][k] for k in ("UserPromptSubmit", "SessionStart", "SessionStartCompact", "allow")):
        target = layout.runner("user")
        copies = [(layout.extension / "runner" / name, target / name) for name in RUNNERS]
        if layout.prices and answers.get("cost", "api") == "api":
            copies.append((layout.prices, target / layout.prices.name))
    return changes, copies, want


def describe(changes, copies, want):
    lines = []
    for change in changes:
        lines.append("%s, %s scope: %s" % (CLIENT_NAMES[change["client"]], change["scope"], change["file"]))
        mine = change["want"]
        for event, label in (("UserPromptSubmit", "UserPromptSubmit"), ("SessionStart", "SessionStart (clear, startup)"),
                             ("SessionStartCompact", "SessionStart (compact)")):
            for line in mine[event]:
                lines.append("  hook %s: %s" % (label, line))
        for rule in mine["deny"]:
            lines.append("  permissions.deny: %s (the tool leaves Claude's context; takes effect in a new session)"
                         % rule)
        for rule in mine["allow"]:
            lines.append("  permissions.allow: %s" % rule)
        if not any(mine.values()):
            lines.append("  remove mem-optimize's entries")
        elif change["client"] == "codex":
            lines.append("  then approve the new hooks in Codex: /hooks in the CLI, or the app's hook review "
                         "(Codex runs a changed hook only once it is trusted)")
            if change["scope"] == "project":
                lines.append("  project hooks load only if Codex trusts this project")
    for source, target in copies:
        lines.append("copy %s -> %s" % (posix(source), posix(target)))
    return "\n".join(lines) or "nothing to change"


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
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".mem-optimize.tmp")
        temporary.write_text(json.dumps(change["after"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)
        previous = log.get(change["file"], {})
        log[change["file"]] = {key: sorted(set(previous.get(key, [])) | set(change["added"].get(key, [])))
                               for key in ("deny", "allow")}
        log[change["file"]].update(backup=posix(backup) if existed else None, applied=stamp)
    setup_log(layout).parent.mkdir(parents=True, exist_ok=True)
    setup_log(layout).write_text(json.dumps(log, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return changes


def reset(layout):
    log, changed = read_log(layout), []
    for _, _, path in targets(layout):
        before = load(path)
        after = strip(json.loads(json.dumps(before)), log.get(posix(path), {}))
        if after != before:
            path.write_text(json.dumps(after, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            changed.append(posix(path))
        log.pop(posix(path), None)
    if setup_log(layout).exists():
        setup_log(layout).write_text(json.dumps(log, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return changed


def status(layout):
    log, report = read_log(layout), {}
    for client, scope, path in targets(layout):
        settings, recorded = load(path), log.get(posix(path), {})
        hooks = [h.get("command") for groups in (settings.get("hooks") or {}).values() for g in groups if ours(g)
                 for h in g.get("hooks") or []]
        permissions = settings.get("permissions") or {}
        report[client + ":" + scope] = {
            "file": posix(path), "hooks": hooks,
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
    parser.add_argument("--client", choices=CLIENTS, help="touch only this client's files (default: both)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()
    layout = Layout(args)
    if args.action in ("plan", "apply"):
        if args.answers is None:
            parser.error(args.action + " needs --answers")
        answers = json.loads(args.answers.read_text(encoding="utf-8-sig"))
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
