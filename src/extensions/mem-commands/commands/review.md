# `MEM REVIEW <target>`

- **mode**: read-only
- **target**: required
- **shell**: none
- **external**: none

Assess a plan, task, or troubleshooting document **before or independently of** its implementation.

Shared rules — target resolution, evidence labelling, severity, verdicts, report format — are in
[../index.md](../index.md).

## What this command assumes

That the work described **has not necessarily been done**. `REVIEW` judges the document: whether it is clear,
complete, coherent, and feasible.

It **must not** treat an unimplemented plan as a defect, and **must not** issue a verdict on an implementation
that is not what was asked about. Existing code may be inspected to assess feasibility and coherence — that is
different from assessing completion, which is what [check.md](check.md) does.

## Procedure

1. Read the target.
2. Read the linked documentation, and the KB pages the target depends on: relevant `architecture/`,
   `conventions/`, and `decisions/`.
3. Inspect the current source where it bears on feasibility or on conflicts with what exists.
4. Assess the dimensions below.
5. Produce the report.

## What to assess

**The document itself** — clarity of the objective; completeness; missing requirements; implicit assumptions;
undeclared dependencies; internal inconsistencies; work described in unverifiable terms; work too broad to be
decomposed.

**Acceptance** — absent or insufficient acceptance criteria; completion conditions that cannot be checked;
missing tests.

**Risk** — technical risk; regression risk; security concerns; concurrency or consistency concerns where they
apply; unhandled edge cases.

**Fit with the project** — architectural incompatibility; conflicts with an existing ADR; conflicts with a
documented convention; conflicts with existing architecture or documentation; divergence from the current code;
missing documentation or MEM updates the plan should produce.

Not every dimension applies to every target. Mark those that do not as `Not applicable` rather than omitting
them silently.

## Build and test section

State that the implementation was not the subject of this command. Do not run build or test commands: nothing
here depends on them.
