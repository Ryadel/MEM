"""Command line entry point for the mem-cleaner runner.

Invoked as source, from wherever the extension was installed:

    python <KB_ROOT>/extensions/mem-cleaner/runner/cli.py status

Reporting, classification, attribution, transactions and validation are all
present. `run` and `test` still refuse for one remaining reason: **no provider
ships yet**, so there is nothing for a pipeline to resolve to. That is the
ordering the whole design rests on -- the machinery that protects a file exists
before anything that can alter one.

Standard library only. Providers are invoked as subprocesses, never imported,
so this package has no dependencies to install into a consuming repository.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

if __package__ in (None, ""):
    # Running the file directly, which is how a consuming project invokes it.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "runner"

from runner import approval as approval_module  # noqa: E402
from runner import attribution as attribution_module  # noqa: E402
from runner import config as config_module  # noqa: E402
from runner import execute as execute_module  # noqa: E402
from runner import pipeline as pipeline_module  # noqa: E402
from runner import regions as regions_module  # noqa: E402
from runner import registry as registry_module  # noqa: E402
from runner import state as state_module  # noqa: E402
from runner import transaction as transaction_module  # noqa: E402
from runner import validation as validation_module  # noqa: E402


VERSION = "0.1.0"
MINIMUM_PYTHON = (3, 8)

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_MISUSE = 2


def main(argv=None):
    if sys.version_info < MINIMUM_PYTHON:
        _err("mem-cleaner needs Python %d.%d or newer" % MINIMUM_PYTHON)
        return EXIT_REFUSED

    parser = _build_parser()
    args = parser.parse_args(argv)

    kb_root = args.kb_root or config_module.find_kb_root()
    if kb_root is None:
        _err("no knowledge base found: no MEM.md in this directory or any parent")
        _err("pass --kb-root to name one explicitly")
        return EXIT_REFUSED

    try:
        cfg = config_module.load(kb_root)
    except config_module.ConfigError as error:
        _err("configuration is invalid: %s" % error)
        return EXIT_REFUSED

    handler = {
        "status": cmd_status,
        "providers": cmd_providers,
        "pipelines": cmd_pipelines,
        "validate-pipeline": cmd_validate_pipeline,
        "recover": cmd_recover,
        "classify": cmd_classify,
        "record": cmd_record,
        "recorded": cmd_recorded,
        "forget": cmd_forget,
        "approve": cmd_approve,
        "run": cmd_run,
        "test": cmd_run,
    }[args.command]

    # An interrupted run is resolved before anything else, whatever was asked
    # for. Reporting on a tree that is mid-transaction would describe a state
    # nobody intended.
    if args.command not in ("recover",):
        outstanding = transaction_module.pending(kb_root)
        if outstanding:
            _err(
                "%d interrupted run(s) found. Run `recover` before anything else."
                % len(outstanding)
            )
            return EXIT_REFUSED

    return handler(args, cfg)


def cmd_status(args, cfg):
    print("mem-cleaner runner %s" % VERSION)
    print("python           %d.%d.%d" % sys.version_info[:3])
    print("interpreter      %s" % sys.executable)
    print("kb root          %s" % cfg.kb_root)
    print("config           %s" % (cfg.source or "(none; defaults in effect)"))
    print("state            %s" % state_module.describe(cfg.kb_root))
    print("")

    for key, value in cfg.describe():
        print("%-18s %s" % (key, value))

    if cfg.problems:
        print("")
        print("Configuration could not be read in full:")
        for problem in cfg.problems:
            print("  - %s" % problem)
        print("Values not read are defaults, and defaults are not consent.")

    if cfg.mode_was_defaulted:
        print("")
        print("mode was absent or unreadable, so it is `manual`.")
        print("A missing setting is never consent.")

    print("")
    print("Validation at level %r:" % cfg.validation)
    try:
        needed = validation_module.commands_for(cfg.validation, cfg)
    except validation_module.Unsatisfiable as error:
        print("  UNSATISFIABLE: %s" % error)
        print("  An escalation that cannot be satisfied is a refusal, not a")
        print("  downgrade. Configure the command, or lower the level.")
    else:
        print("  minimum          always (integrity, encoding, line endings, syntax)")
        for name, command in needed:
            print("  %-16s %s" % (name, command if command else "not configured; unchecked"))
        if not needed:
            print("  (no project command runs at this level)")

    registry = registry_module.load(cfg.extension_root)
    pipelines, pipeline_problems = pipeline_module.load(cfg.extension_root)
    print("")
    print("providers        %d" % len(registry))
    print("pipelines        %d" % len(pipelines))

    selected = pipelines.get(cfg.pipeline)
    if selected is None:
        print("")
        print("Configured pipeline %r is not defined." % cfg.pipeline)
    else:
        resolution = pipeline_module.resolve(
            selected, registry, cfg.max_rewrite_stages, explicit_target=False
        )
        print("")
        print("Pipeline %s:" % selected.id)
        for stage in selected.stages:
            binding = resolution.bindings.get(stage.index)
            if stage.builtin is not None:
                bound = "builtin"
            elif binding is None:
                bound = "UNRESOLVED"
            else:
                bound = binding[0].id
            print("  %d. %-34s %s" % (stage.index, stage.describe(), bound))
        if not resolution.runnable:
            print("")
            print("Not runnable:")
            for problem in resolution.problems:
                print("  - %s" % problem)

    _report_problems(registry.problems + pipeline_problems)
    return EXIT_OK


def cmd_providers(args, cfg):
    registry = registry_module.load(cfg.extension_root)
    if not len(registry):
        print("No providers are defined.")
        print("")
        print("This is expected at 0.1.0: the transaction core, the region")
        print("classifier and the validation layer ship before anything that")
        print("can alter a file.")
    for provider in registry.all():
        print("%s" % provider.id)
        print("  source      %s" % provider.source)
        print("  license     %s" % (provider.license or "(undeclared)"))
        print("  type        %s" % provider.type)
        for operation in provider.operations.values():
            print(
                "  %-12s role=%-9s capability=%-20s deterministic=%s"
                % (
                    operation.name,
                    operation.role,
                    operation.capability,
                    operation.deterministic,
                )
            )
        print("")
    _report_problems(registry.problems)
    return EXIT_OK


def cmd_pipelines(args, cfg):
    registry = registry_module.load(cfg.extension_root)
    pipelines, problems = pipeline_module.load(cfg.extension_root)
    if not pipelines:
        print("No pipelines are defined.")
    for key in sorted(pipelines):
        pipeline = pipelines[key]
        resolution = pipeline_module.resolve(
            pipeline, registry, cfg.max_rewrite_stages, explicit_target=False
        )
        marker = "runnable" if resolution.runnable else "not runnable"
        default = " (configured default)" if key == cfg.pipeline else ""
        print("%s -- %s%s" % (pipeline.id, marker, default))
        for stage in pipeline.stages:
            print("  %d. %s" % (stage.index, stage.describe()))
        for problem in resolution.problems:
            print("  ! %s" % problem)
        print("")
    _report_problems(problems)
    return EXIT_OK


def cmd_validate_pipeline(args, cfg):
    registry = registry_module.load(cfg.extension_root)
    pipelines, problems = pipeline_module.load(cfg.extension_root)
    _report_problems(problems)

    pipeline = pipelines.get(args.pipeline)
    if pipeline is None:
        _err("no pipeline named %r" % args.pipeline)
        return EXIT_REFUSED

    resolution = pipeline_module.resolve(
        pipeline,
        registry,
        cfg.max_rewrite_stages,
        explicit_target=args.explicit_target,
    )
    if resolution.runnable:
        print("%s: ok" % pipeline.id)
        return EXIT_OK

    print("%s: refused" % pipeline.id)
    for problem in resolution.problems:
        print("  - %s" % problem)
    return EXIT_REFUSED


def cmd_recover(args, cfg):
    outstanding = transaction_module.pending(cfg.kb_root)
    if not outstanding:
        print("Nothing to recover.")
        return EXIT_OK

    print("%d interrupted run(s):" % len(outstanding))
    print("")
    results = transaction_module.recover(cfg.kb_root)
    refused = 0
    for result in results:
        print("%s" % os.path.basename(result.path))
        print("  recorded state  %s" % result.journal.get("state", "?"))
        print("  pipeline        %s" % result.journal.get("pipeline", "?"))
        print("  action          %s" % result.action)
        for conflict in result.conflicts:
            refused += 1
            print("  ! %s" % conflict)
        print("")

    if refused:
        print("Some files were left as they are, deliberately: they changed after")
        print("the interrupted run installed its candidate. Finishing the rollback")
        print("would have destroyed newer work. Resolve those by hand; the journal")
        print("stays on disk until you do.")
        return EXIT_REFUSED
    return EXIT_OK


def cmd_classify(args, cfg):
    """Show how a file is classified, and what a scope would allow."""
    if not os.path.isfile(args.target):
        _err("%s: no such file" % args.target)
        return EXIT_REFUSED

    with open(args.target, "rb") as handle:
        data = handle.read()
    result = regions_module.classify(args.target, data)

    print("%s" % args.target)
    print("  classifier   %s" % result.language)
    if result.note:
        print("  note         %s" % result.note)

    if not result.usable:
        print("")
        print("No classifier means no touchable region -- not 'all prose'.")
        print("A scoped stage refuses this file rather than guessing at it.")
        return EXIT_OK

    counts = result.summary()
    print("  regions      %s" % (", ".join("%s=%d" % kv for kv in sorted(counts.items())) or "none"))
    print("")
    for scope in ("prose", "runtime", "any"):
        ranges = regions_module.touchable_ranges(result, scope)
        covered = sum(end - start for start, end in ranges)
        print(
            "  scope %-8s %d region(s), %d of %d bytes"
            % (scope, len(ranges), covered, len(data))
        )

    if args.show:
        print("")
        for region in result.regions:
            text = data[region.start : region.end].decode("utf-8", "replace")
            text = text.strip().replace("\n", " ")
            if text:
                print("  %-10s %s" % (region.kind, text[:66]))
    return EXIT_OK


def cmd_record(args, cfg):
    """Record files the agent has just written. Called after the last write."""
    record = attribution_module.Record(cfg.kb_root, args.session)
    added = []
    failed = []
    for path in args.target:
        try:
            entry = record.add(path)
        except ValueError as error:
            failed.append(str(error))
            continue
        added.append(entry)
    record.save()

    for entry in added:
        print("recorded %s" % attribution_module.relative_to(entry.path, cfg.project_root))
    for message in failed:
        _err(message)
    print("session %s holds %d file(s)" % (args.session, len(record)))
    return EXIT_REFUSED if failed else EXIT_OK


def cmd_recorded(args, cfg):
    """Show a session's record, and what would actually be eligible."""
    known = attribution_module.sessions(cfg.kb_root)
    if args.session is None:
        if not known:
            print("No session records on this host.")
            return EXIT_OK
        print("Sessions with a record:")
        for name in known:
            print("  %s" % name)
        print("")
        print("Pass --session to see one.")
        return EXIT_OK

    record = attribution_module.Record(cfg.kb_root, args.session)
    if not len(record):
        print("Session %s has no record." % args.session)
        return EXIT_OK

    eligible, skipped = attribution_module.select(record, cfg)
    print("Session %s: %d recorded, %d eligible" % (args.session, len(record), len(eligible)))
    print("")
    for entry in eligible:
        print("  %s" % attribution_module.relative_to(entry.path, cfg.project_root))
    for path, reason in skipped:
        print("  %-58s SKIPPED: %s" % (attribution_module.relative_to(path, cfg.project_root), reason))

    if any(reason == attribution_module.CHANGED for _, reason in skipped):
        print("")
        print("A changed file means a human edited it after the agent wrote it.")
        print("That edit is not the agent's output to clean.")
    return EXIT_OK


def cmd_forget(args, cfg):
    record = attribution_module.Record(cfg.kb_root, args.session)
    count = len(record)
    record.forget()
    print("session %s: %d record(s) dropped" % (args.session, count))
    return EXIT_OK


# Which validation level a scope's changes demand. Extraction guarantees the
# change is inside the scope, so the scope is enough to decide -- no diff needed.
_SCOPE_DEMANDS = {"prose": "syntax", "runtime": "tests", "any": "tests"}


def cmd_run(args, cfg):
    """Run a pipeline over explicit targets, or over this session's record."""
    dry = args.command == "test"

    registry = registry_module.load(cfg.extension_root)
    pipelines, problems = pipeline_module.load(cfg.extension_root)
    _report_problems(problems)

    name = args.pipeline or cfg.pipeline
    pipeline = pipelines.get(name)
    if pipeline is None:
        _err("no pipeline named %r" % name)
        return EXIT_REFUSED

    explicit = bool(args.target)
    resolution = pipeline_module.resolve(
        pipeline, registry, cfg.max_rewrite_stages, explicit_target=explicit
    )
    if not resolution.runnable:
        _err("pipeline %r cannot run:" % pipeline.id)
        for problem in resolution.problems:
            _err("  %s" % problem)
        return EXIT_REFUSED

    if getattr(args, "automatic", False):
        approval = approval_module.Approval(cfg.kb_root)
        allowed, reason = approval_module.check(
            cfg, approval, approval_module.fingerprint(cfg, pipeline, resolution)
        )
        if not allowed:
            _err("unattended run refused: %s" % reason)
            return EXIT_REFUSED

    targets, skipped = _targets(args, cfg, explicit)
    for path, reason in skipped:
        print("skipped %-52s %s" % (attribution_module.relative_to(path, cfg.project_root), reason))
    if not targets:
        print("Nothing to do.")
        return EXIT_OK

    # Stages first, on content in memory. Nothing reaches the disk until every
    # target has come through cleanly.
    candidates = {}
    demanded = "syntax"
    for path, _ in targets:
        with open(path, "rb") as handle:
            data = original = handle.read()
        for stage in pipeline.stages:
            binding = resolution.bindings.get(stage.index)
            if binding is None or stage.role != "transform":
                continue
            provider, operation = binding
            try:
                outcome = execute_module.run_stage(
                    provider, operation, stage, data, path, cfg.project_root
                )
            except execute_module.StageError as error:
                _err("stage %d on %s: %s" % (stage.index, os.path.basename(path), error))
                return EXIT_REFUSED
            if outcome.changed:
                scope = getattr(stage, "regions", "any")
                if validation_module.rank(_SCOPE_DEMANDS.get(scope, "tests")) > validation_module.rank(demanded):
                    demanded = _SCOPE_DEMANDS.get(scope, "tests")
            data = outcome.data
            if outcome.report:
                print("  stage %d %-22s %s" % (stage.index, operation.name, outcome.report.replace("\n", " ")[:80]))
        if data != original:
            candidates[path] = data

    if not candidates:
        print("Nothing changed.")
        return EXIT_OK

    level = validation_module.required_level(cfg.validation, demanded)
    try:
        validation_module.commands_for(level, cfg)
    except validation_module.Unsatisfiable as error:
        _err("this change demands validation level %r: %s" % (level, error))
        _err("An escalation that cannot be satisfied is a refusal, not a downgrade.")
        return EXIT_REFUSED

    if dry:
        print("")
        print("%d file(s) would change; validation would run at %r." % (len(candidates), level))
        for path in sorted(candidates):
            print("  %s" % attribution_module.relative_to(path, cfg.project_root))
        print("Nothing was written.")
        return EXIT_OK

    return _commit(cfg, pipeline, targets, candidates, level, args.session)


def _commit(cfg, pipeline, targets, candidates, level, session_record=None):
    session = "run-%d" % os.getpid()
    transaction = transaction_module.Transaction(cfg.kb_root, session, pipeline.id)
    try:
        transaction.prepare([t for t in targets if t[0] in candidates])
    except transaction_module.TransactionError as error:
        _err(str(error))
        return EXIT_REFUSED

    staged = {}
    for path, data in candidates.items():
        handle, temporary = tempfile.mkstemp(prefix="mem-cleaner-cand-")
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        staged[path] = temporary

    try:
        transaction.install(staged)
    except transaction_module.TransactionError as error:
        _err(str(error))
        transaction.rollback("install refused")
        return EXIT_REFUSED

    transaction.validating()
    pairs = [(entry.backup, entry.path) for entry in transaction.entries]
    report = validation_module.full(pairs, cfg, level)
    for finding in report.findings:
        print("  %s" % finding)

    if report.ok:
        transaction.commit()
        _rebaseline(cfg, session_record, candidates)
        print("")
        print("%d file(s) updated, validated at %r." % (len(candidates), level))
        return EXIT_OK

    conflicts = transaction.rollback("validation failed")
    print("")
    print("Validation failed; %d file(s) restored." % len(candidates))
    for conflict in conflicts:
        print("  ! %s" % conflict)
    return EXIT_REFUSED


def _targets(args, cfg, explicit):
    """(path, expected_hash) pairs, plus what was skipped and why."""
    if explicit:
        # An explicit target is a user instruction, not an attribution claim,
        # so it carries no expected hash.
        return [(os.path.abspath(t), None) for t in args.target], []

    if not args.session:
        _err("without a target, --session names the record to clean")
        return [], []
    record = attribution_module.Record(cfg.kb_root, args.session)
    eligible, skipped = attribution_module.select(record, cfg)
    return [(entry.path, entry.expected_hash) for entry in eligible], skipped


def _rebaseline(cfg, session, candidates):
    """Re-record what we just wrote, so our own edit is not read as a human's.

    The attribution record holds the hash the agent left behind. Cleaning
    changes it, and the next run would then skip the file as `changed since
    recorded` -- attributing our own write to a person. Re-recording keeps the
    file attributed to the agent, which it still is: the agent wrote it, this
    only tidied what it may touch.
    """
    if not session:
        return
    record = attribution_module.Record(cfg.kb_root, session)
    touched = 0
    for path in candidates:
        if path in record.entries:
            record.add(path)
            touched += 1
    if touched:
        record.save()
        print("re-recorded %d file(s) in session %s" % (touched, session))


def cmd_approve(args, cfg):
    """Record, show or revoke the approval that unattended runs rest on."""
    approval = approval_module.Approval(cfg.kb_root)

    if args.revoke:
        approval.revoke()
        print("Approval revoked. Unattended runs refuse until one is given again.")
        return EXIT_OK

    registry = registry_module.load(cfg.extension_root)
    pipelines, _ = pipeline_module.load(cfg.extension_root)
    pipeline = pipelines.get(cfg.pipeline)
    if pipeline is None:
        _err("configured pipeline %r is not defined" % cfg.pipeline)
        return EXIT_REFUSED
    resolution = pipeline_module.resolve(
        pipeline, registry, cfg.max_rewrite_stages, explicit_target=False
    )
    current = approval_module.fingerprint(cfg, pipeline, resolution)

    if args.mode is None:
        print("configured mode   %s" % cfg.mode)
        print("approved mode     %s" % (approval.mode or "(none)"))
        print("approval          %s" % ("current" if approval.fingerprint == current else "lapsed or absent"))
        if approval.note:
            print("note              %s" % approval.note)
        allowed, reason = approval_module.check(cfg, approval, current)
        print("")
        print("unattended runs   %s" % ("permitted" if allowed else "refused: " + reason))
        return EXIT_OK

    if args.mode not in approval_module.MODES:
        _err("mode must be one of: %s" % ", ".join(approval_module.MODES))
        return EXIT_REFUSED
    if not resolution.runnable:
        _err("refusing to approve a pipeline that cannot run:")
        for problem in resolution.problems:
            _err("  %s" % problem)
        return EXIT_REFUSED

    approval.save(args.mode, current, args.note or "")
    print("Approved mode %r for pipeline %r." % (args.mode, pipeline.id))
    print("It lapses if the pipeline, a provider, the rewrite limit or the")
    print("validation level changes.")
    return EXIT_OK


def cmd_not_yet(args, cfg):
    _err("%r is not implemented at %s." % (args.command, VERSION))
    _err("Transactions, validation, region scoping and attribution are all in")
    _err("place. What is missing is a provider: no pipeline can resolve, so")
    _err("there is nothing to run. Refusing is the correct answer, not a gap.")
    return EXIT_REFUSED


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="mem-cleaner",
        description="Run mem-cleaner pipelines over files an agent has written.",
    )
    parser.add_argument("--kb-root", help="knowledge base root; found automatically if omitted")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="configuration, versions and the configured pipeline")
    sub.add_parser("providers", help="providers, their operations and availability")
    sub.add_parser("pipelines", help="pipelines and whether they resolve")

    sub.add_parser("recover", help="resolve an interrupted run")

    classify = sub.add_parser("classify", help="show a file's regions and what a scope allows")
    classify.add_argument("target")
    classify.add_argument("--show", action="store_true", help="list every region")

    record = sub.add_parser("record", help="record files the agent has written")
    record.add_argument("target", nargs="+")
    record.add_argument("--session", required=True)

    recorded = sub.add_parser("recorded", help="show a session's record and eligibility")
    recorded.add_argument("--session")

    forget = sub.add_parser("forget", help="drop a session's record")
    forget.add_argument("--session", required=True)

    approve = sub.add_parser("approve", help="record, show or revoke the autonomy approval")
    approve.add_argument("--mode", help="automatic | confirm | manual; omit to show")
    approve.add_argument("--note", help="why this was approved")
    approve.add_argument("--revoke", action="store_true")

    validate = sub.add_parser("validate-pipeline", help="check one pipeline")
    validate.add_argument("pipeline")
    validate.add_argument(
        "--explicit-target",
        action="store_true",
        help="check as though invoked against a named file",
    )

    run = sub.add_parser("run", help="run a pipeline and replace the targets")
    run.add_argument("target", nargs="*")
    run.add_argument("--pipeline")
    run.add_argument("--session")
    run.add_argument("--automatic", action="store_true",
                     help="an unattended run; requires a current approval")

    test = sub.add_parser("test", help="run a pipeline and report, changing nothing")
    test.add_argument("target", nargs="*")
    test.add_argument("--pipeline")
    test.add_argument("--session")
    return parser


def _report_problems(problems):
    if not problems:
        return
    print("")
    print("Refused definitions:")
    for problem in problems:
        print("  - %s" % problem)


def _err(message):
    sys.stderr.write("mem-cleaner: %s\n" % message)


if __name__ == "__main__":
    sys.exit(main())
