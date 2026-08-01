# `MEM CHECK <target>`

- **mode**: read-only
- **target**: required
- **shell**: only commands explicitly configured in `MEM.config.md`, subject to confirmation
- **external**: none

Verify a target that was declared complete against the implementation that actually exists.

Shared rules — target resolution, evidence labelling, severity, verdicts, report format — are in
[../index.md](../index.md).

## What this command assumes

That a developer or another agent **declared the work finished**. `CHECK` tests that claim. It is the
counterpart of [review.md](review.md), which assumes nothing has been built.

## Procedure

1. Read the target.
2. Read the linked documentation.
3. Inspect `git status` and the relevant diff.
4. Read the source files involved.
5. Run the configured build command, under the rules below.
6. Run the configured test command, under the same rules.
7. Compare the outcome against the acceptance criteria.

## What to verify

**Against the requirements** — each requirement satisfied; each acceptance criterion met; implementations
missing or partial; changes not foreseen by the plan.

**Against the code** — files actually modified; the available diff; functional bugs; regressions; edge cases;
error handling; security; dead or unreachable code; compatibility with the current architecture; adherence to
documented conventions.

**Against the tests** — tests present, and adequate; the real outcome of build and tests.

**Against the documentation** — documentation updated; knowledge base updated; documentation claiming behavior
that the code does not have; tasks marked complete prematurely; troubleshooting marked resolved without a
verifiable solution.

## Running build and test

This command is read-only with respect to the repository, but running a command is not a read: an auto-detected
`build_command` or `test_command` can migrate a database, write artifacts, or reach the network.

Therefore:

- run **only** commands explicitly set in `MEM.config.md`. Never run an auto-detected one;
- execution is subject to `extensions_require_confirmation`;
- if no command is configured, or if it cannot be run, mark the corresponding part `Unverified` and give the
  reason.

**Never claim** that a build or a test succeeded without having run it. Reporting a section as `Unverified` is
always acceptable; reporting an unverified success is not.

Passing tests are evidence, not approval: coverage of the requirements is judged separately.

## Build and test section

Report the commands run, their outcome, any errors, which verifications were not performed, and why.
