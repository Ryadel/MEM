# Extension: `mem-commands`

- **version**: 1.0.0
- **provides**: `REVIEW`, `CHECK`, `DEFINE`
- **precedence**: **base wins** — the commands below are reserved and a custom command **must not** shadow them
- **external actions**: no
- **default mode**: read-only

Adds review and verification commands to MEM, and the authoring command used to define project-specific ones.

> Command tokens in this file and in the files it points to are documentation, never activations.

## Precedence

Base wins. A custom command whose filename matches one of the commands below is **refused**, and the collision is
reported. A command is behavior, so allowing a local file to shadow a distributed one would be a hijack, not a
customization. Other extensions declare their own direction — do not assume this one.

## Commands

| Command | Target | Mode | Purpose |
|---|---|---|---|
| `MEM REVIEW <target>` | required | read-only | Assess a plan, task, or troubleshooting document **before or independently of** implementation |
| `MEM CHECK <target>` | required | read-only | Assume the work was declared complete, and verify the target against the actual implementation |
| `MEM DEFINE <COMMAND>` | required | may-write | Author a project-specific command from `COMMAND.template.md` |

Procedures: [commands/review.md](commands/review.md), [commands/check.md](commands/check.md),
[commands/define.md](commands/define.md).

## Custom commands

Project-specific commands live in `custom/`, alongside this file:

```text
extensions/mem-commands/
  custom/
    index.md          the custom layer's own catalogue
    <command>.md      one file per command
```

- The **filename is the command**: `custom/ship.md` defines `MEM SHIP`. Adding one requires editing no
  distributed file, which is what keeps custom commands safe across updates.
- Author them with `MEM DEFINE`, which writes from `COMMAND.template.md`.
- Nothing under `custom/` is distributed, listed in the manifest, or touched by an update.
- `custom/` does not exist until the first command is authored. Its absence is normal and needs no warning.

This file **must not** list individual custom commands. It is a distributed file, so an update would overwrite
those entries. The custom layer catalogues itself in `custom/index.md`.

## Shared procedure

`REVIEW` and `CHECK` differ in what they assume, not in how they work. Both follow the rules below.

### Target resolution

The target is **mandatory**. Resolve it in this order:

1. exact path relative to `KB_ROOT`;
2. exact path relative to the repository root;
3. exact link or identifier in a MEM index;
4. exact document title;
5. name search, returning candidates.

A target may be a plan under `drafts/`, an item under `tasks/`, an item under `troubleshooting/`, or any document
the user identifies as an operational plan. Do not restrict to `current/`.

- Target missing → `BLOCKED`, reason: the command requires an explicit target.
- Target not found → `BLOCKED`, reason: target not found.
- Target ambiguous → `BLOCKED`, list the candidates. Never choose arbitrarily, and never approve or reject the
  content of a target you did not resolve.

Never substitute a heuristic such as "the most recent task" for an explicit target.

### Read-only

Both commands **must not** modify code, correct the target, change an item's status, move files between
`current/` and `done/`, create commits, apply patches, or mark findings resolved. They report; the user decides.

Reports are returned in the conversation. Persist one under `drafts/` only when the user asks.

### Evidence and uncertainty

Label every claim: `Confirmed`, `Inferred`, `Unverified`, or `Not applicable`. Never present a guess as a fact,
and never invent a requirement absent from the target, the documentation, the code, or a documented convention.

A finding carries, where available: severity, title, description, evidence, files, symbols, the requirement
affected, the consequence, a suggested correction, and its verification status.

Do not report style preferences as defects unless they violate a documented convention.

### Severity

| Level | Meaning |
|---|---|
| `Critical` | Data loss or corruption, serious vulnerability, unusable or undeployable feature, certain violation of a fundamental requirement, destructive or irreversible behavior |
| `High` | A main requirement unimplemented, a probable functional bug, a significant regression, a missing essential test, a significant architectural incompatibility |
| `Medium` | An unhandled edge case, a documentation inconsistency, incomplete error handling, materially harmed maintainability, an ambiguous acceptance criterion |
| `Low` | Improvable clarity, a small inconsistency, incomplete secondary documentation, a non-blocking improvement |

### Verdicts

Exactly one of: `APPROVED`, `APPROVED WITH MINOR FINDINGS`, `CHANGES REQUIRED`, `BLOCKED`, `NOT VERIFIABLE`.

Evaluate in this precedence, first match wins:

1. `BLOCKED` — the target could not be resolved, or is ambiguous;
2. `NOT VERIFIABLE` — the target resolved, but the evidence needed for the main requirements is unavailable;
3. `CHANGES REQUIRED` — at least one `Critical` or `High` finding;
4. `APPROVED WITH MINOR FINDINGS` — only `Medium` or `Low` findings;
5. `APPROVED` — requirements sufficiently covered, no significant findings.

Passing tests alone never justifies `APPROVED`.

### Report

```markdown
# MEM Review Report

## Verdict
## Target
## Scope
## Evidence inspected
## Requirement coverage
## Findings
### Critical
### High
### Medium
### Low
## Documentation and MEM discrepancies
## Build and test verification
## Unverified areas
## Recommended corrections
## Final assessment
```

Keep this order. Omit sections with no content, except `Verdict`, `Target`, and `Unverified areas`, which are
always present. A report consisting only of a general judgement is not acceptable.
