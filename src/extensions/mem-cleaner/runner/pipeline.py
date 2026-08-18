"""Loads pipeline definitions and validates them before anything runs.

Validation is refusal, not repair. A pipeline that breaks a rule is rejected
whole, with the offending stage named, because the alternative -- running the
part that looked fine -- is how a guarantee becomes a suggestion.
"""

from __future__ import annotations

import os

from . import frontmatter
from .models import (
    DefinitionError,
    Pipeline,
    RESTRICTED_CAPABILITIES,
    effective_regions,
    regions_permit,
)


class Problem:
    """One reason a pipeline cannot run, in the order stages appear."""

    def __init__(self, stage_index, message):
        self.stage_index = stage_index
        self.message = message

    def __str__(self):
        if self.stage_index is None:
            return self.message
        return "stage %d: %s" % (self.stage_index, self.message)


class Resolution:
    """The outcome of checking one pipeline against one registry."""

    def __init__(self, pipeline, bindings, problems, scopes=None):
        self.pipeline = pipeline
        self.bindings = bindings
        self.problems = problems
        # Effective region scope per stage: the narrower of what the stage
        # requested and what the bound operation permits.
        self.scopes = scopes or {}

    @property
    def runnable(self):
        return not self.problems


def load(extension_root):
    """Load base and custom pipeline definitions. Returns (dict, problems)."""
    pipelines = {}
    problems = []
    seen = {}

    for directory, is_custom in (
        (os.path.join(extension_root, "pipelines"), False),
        (os.path.join(extension_root, "custom", "pipelines"), True),
    ):
        if not os.path.isdir(directory):
            continue
        names = sorted(
            name
            for name in os.listdir(directory)
            if name.endswith(".md") and name != "index.md" and not name.startswith("_")
        )
        for name in names:
            path = os.path.join(directory, name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data, _ = frontmatter.load(handle.read())
                if not data:
                    raise DefinitionError("%s: no front matter" % path)
                pipeline = Pipeline(data, path)
            except (DefinitionError, frontmatter.FrontMatterError) as error:
                problems.append(str(error))
                continue

            if is_custom and not pipeline.is_custom:
                problems.append(
                    "%s: a custom pipeline id must be namespaced 'custom/<id>'" % path
                )
                continue
            if pipeline.id in seen:
                problems.append(
                    "%s: id %r already defined by %s; collisions are refused"
                    % (path, pipeline.id, seen[pipeline.id])
                )
                continue

            seen[pipeline.id] = path
            pipelines[pipeline.id] = pipeline

    return pipelines, problems


def resolve(pipeline, registry, max_rewrite_stages, explicit_target=False):
    """Bind every stage to a provider operation and check the pipeline's rules."""
    problems = []
    bindings = {}
    scopes = {}

    for stage in pipeline.stages:
        if stage.builtin is not None:
            bindings[stage.index] = None
            continue

        if stage.capability in RESTRICTED_CAPABILITIES and not explicit_target:
            # Attribution and provenance stages never run against a glob. The
            # rule lives here so the validator enforces it, not the prose.
            problems.append(
                Problem(
                    stage.index,
                    "%s requires an explicitly named target" % stage.capability,
                )
            )

        candidates = registry.resolve(stage.capability, stage.role, stage.provider_id)
        if not candidates:
            if stage.is_pinned:
                message = "provider %r cannot %s %s" % (
                    stage.provider_id,
                    stage.role,
                    stage.capability,
                )
            else:
                message = "no available provider can %s %s" % (stage.role, stage.capability)
            problems.append(Problem(stage.index, message))
            continue

        # Region scope is part of the match, not an afterthought applied later.
        # A stage asking for a region the operation will not touch is refused
        # here; otherwise the boundary would exist only in the prose.
        usable = [
            pair for pair in candidates if regions_permit(pair[1].regions, stage.regions)
        ]
        if not usable:
            offered = ", ".join(sorted({pair[1].regions for pair in candidates}))
            problems.append(
                Problem(
                    stage.index,
                    "requests regions %r but the available operation(s) touch %s"
                    % (stage.regions, offered),
                )
            )
            continue

        provider, operation = usable[0]
        bindings[stage.index] = (provider, operation)
        scopes[stage.index] = effective_regions(operation.regions, stage.regions)

    # A rewrite is a writing stage bound to a non-deterministic operation.
    # Deterministic transforms are unlimited: chaining two of them is the
    # ordinary shape of the `safe` profile. Unresolved stages cannot be
    # classified, but they are already refused above, so the pipeline does not
    # run on the strength of an undercount.
    rewrites = []
    for stage in pipeline.writing_stages:
        binding = bindings.get(stage.index)
        if binding is None:
            continue
        _, operation = binding
        if not operation.deterministic:
            rewrites.append(stage)

    if len(rewrites) > max_rewrite_stages:
        problems.append(
            Problem(
                None,
                "%d rewrite stages declared (%s), maximum configured is %d"
                % (
                    len(rewrites),
                    ", ".join("stage %d" % s.index for s in rewrites),
                    max_rewrite_stages,
                ),
            )
        )

    # A pipeline that rewrites and never checks its own output is refused: the
    # transactional promise depends on something to validate against.
    if rewrites and not any(s.role == "validate" for s in pipeline.stages):
        problems.append(
            Problem(None, "a pipeline with a rewrite stage must contain a validate stage")
        )

    return Resolution(pipeline, bindings, problems, scopes)
