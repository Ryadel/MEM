"""Value types shared by the registry, the pipeline parser and the CLI.

Deliberately dumb: no behaviour beyond validating its own shape. The rules that
say what a pipeline may contain live in pipeline.py, and the rules about what a
provider can do live in the provider definition itself.
"""

from __future__ import annotations


ROLES = ("inspect", "transform", "validate")

# Roles that produce a candidate file. NOT the same as the rewrite limit: a
# deterministic transform chains freely, and only a non-deterministic one -- a
# rewrite -- is counted. That distinction cannot be made from the stage alone,
# because determinism is a property of the bound operation, so the counting
# happens in pipeline.resolve() after binding.
WRITING_ROLES = ("transform",)

REGIONS = ("prose", "runtime", "any")

# Capabilities a distributed pipeline may request. A project may invent others
# for its own provider and its own pipeline; nothing shipped will name them.
CAPABILITIES = (
    "unicode",
    "metadata-technical",
    "metadata-attribution",
    "c2pa",
    "statistical-rewrite",
    "paraphrase",
)

# Capabilities excluded from default pipelines and from wildcard automation.
# Enforced by the pipeline validator, not by documentation.
RESTRICTED_CAPABILITIES = ("metadata-attribution", "c2pa")

BUILTIN_VALIDATORS = ("syntax", "format", "project")


class DefinitionError(ValueError):
    """A definition file is malformed or outside the accepted schema."""


class Operation:
    """One thing a provider can do, in one role."""

    def __init__(self, provider_id, name, data, source):
        self.provider_id = provider_id
        self.name = name
        self.source = source

        self.role = _require(data, "role", str, name, source)
        if self.role not in ROLES:
            raise DefinitionError(
                "%s: operation %r has unknown role %r" % (source, name, self.role)
            )

        self.capability = _require(data, "capability", str, name, source)
        self.deterministic = bool(data.get("deterministic", False))
        self.chainable = bool(data.get("chainable", False))
        self.regions = data.get("regions", "any")
        if self.regions not in REGIONS:
            raise DefinitionError(
                "%s: operation %r has unknown regions %r" % (source, name, self.regions)
            )

        allowlist = data.get("allowlist")
        if allowlist is not None and not isinstance(allowlist, list):
            raise DefinitionError("%s: operation %r allowlist must be a list" % (source, name))
        self.allowlist = list(allowlist) if allowlist else []

        # An open-ended capability without an enumerated allowlist is refused.
        # This is what stops a provider gaining a broader mode upstream from
        # silently widening the `safe` profile.
        if self.capability == "metadata-technical" and not self.allowlist:
            raise DefinitionError(
                "%s: operation %r declares metadata-technical without an allowlist"
                % (source, name)
            )

    @property
    def writes(self):
        return self.role in WRITING_ROLES

    def __repr__(self):
        return "<Operation %s/%s role=%s>" % (self.provider_id, self.name, self.role)


class Provider:
    """A provider definition. The engine never branches on its id."""

    def __init__(self, data, source):
        self.source = source
        self.schema = _require(data, "schema", str, "schema", source)
        if self.schema != "provider/1":
            raise DefinitionError("%s: unsupported schema %r" % (source, self.schema))

        self.id = _require(data, "id", str, "id", source)
        self.version = data.get("version", 1)
        self.license = data.get("license")
        self.locality = data.get("locality", "local")

        # Remote providers are refused at 1.0: no file content leaves the host.
        if self.locality != "local":
            raise DefinitionError(
                "%s: locality %r is refused; 1.0 ships no remote provider"
                % (source, self.locality)
            )

        self.type = data.get("type", "adapter")
        self.command = data.get("command")
        args = data.get("args")
        if args is not None and not isinstance(args, list):
            raise DefinitionError("%s: args must be a list" % source)
        self.args = list(args) if args else []

        if self.type == "cli" and not self.command:
            raise DefinitionError("%s: a cli provider must declare a command" % source)

        operations = data.get("operations") or {}
        if not isinstance(operations, dict) or not operations:
            raise DefinitionError("%s: at least one operation is required" % source)
        self.operations = {
            name: Operation(self.id, name, body or {}, source)
            for name, body in operations.items()
        }

    @property
    def is_custom(self):
        return self.id.startswith("custom/")

    def find(self, capability, role):
        """Operations satisfying a capability in a role, in declaration order."""
        return [
            op
            for op in self.operations.values()
            if op.capability == capability and op.role == role
        ]

    def __repr__(self):
        return "<Provider %s>" % self.id


class Stage:
    """One step in a pipeline. Addresses a role and a capability."""

    def __init__(self, data, index, source):
        self.source = source
        self.index = index

        self.builtin = data.get("builtin")
        self.provider_id = data.get("provider")
        self.capability = data.get("capability")

        # Which classified regions this stage may touch in this pipeline. It
        # defaults to `any` and is narrowed further by the bound operation, so
        # a pipeline can restrict a permissive provider but never widen a
        # restrictive one -- see regions_permit().
        self.regions = data.get("regions", "any")
        if self.regions not in REGIONS:
            raise DefinitionError(
                "%s: stage %d has unknown regions %r" % (source, index, self.regions)
            )

        role = data.get("role")
        if self.builtin is not None:
            # A builtin validator is always a validate stage; saying so is
            # optional but must not contradict.
            if self.builtin not in BUILTIN_VALIDATORS:
                raise DefinitionError(
                    "%s: stage %d has unknown builtin %r" % (source, index, self.builtin)
                )
            role = role or "validate"
        if role not in ROLES:
            raise DefinitionError("%s: stage %d has unknown role %r" % (source, index, role))
        self.role = role

        if self.builtin is None and not self.capability:
            raise DefinitionError(
                "%s: stage %d must declare a capability or a builtin" % (source, index)
            )

    @property
    def is_pinned(self):
        return self.provider_id is not None

    @property
    def writes(self):
        return self.role in WRITING_ROLES

    def describe(self):
        if self.builtin:
            return "%s (builtin %s)" % (self.role, self.builtin)
        pin = " via %s" % self.provider_id if self.provider_id else ""
        scope = "" if self.regions == "any" else " [%s]" % self.regions
        return "%s %s%s%s" % (self.role, self.capability, pin, scope)


def regions_permit(operation_regions, stage_regions):
    """Whether an operation may be used for a stage's requested region scope.

    `any` on the operation permits anything. Otherwise the stage must not ask
    for a region the operation does not touch: a stage requesting `runtime`
    from an operation declared `prose` is refused rather than quietly narrowed,
    because the pipeline asked for something that will not happen.
    """
    if operation_regions == "any":
        return True
    if stage_regions == "any":
        # The operation is the narrower of the two, and narrowing is safe.
        return True
    return stage_regions == operation_regions


def effective_regions(operation_regions, stage_regions):
    """The scope actually applied: the narrower of the two."""
    if operation_regions == "any":
        return stage_regions
    if stage_regions == "any":
        return operation_regions
    return stage_regions


class Pipeline:
    def __init__(self, data, source):
        self.source = source
        self.schema = _require(data, "schema", str, "schema", source)
        if self.schema != "pipeline/1":
            raise DefinitionError("%s: unsupported schema %r" % (source, self.schema))

        self.id = _require(data, "id", str, "id", source)
        self.version = data.get("version", 1)

        stages = data.get("stages")
        if not isinstance(stages, list) or not stages:
            raise DefinitionError("%s: at least one stage is required" % source)
        self.stages = [Stage(s or {}, i, source) for i, s in enumerate(stages, start=1)]

    @property
    def is_custom(self):
        return self.id.startswith("custom/")

    @property
    def writing_stages(self):
        return [s for s in self.stages if s.writes]

    def __repr__(self):
        return "<Pipeline %s stages=%d>" % (self.id, len(self.stages))


def _require(data, key, kind, what, source):
    value = data.get(key)
    if not isinstance(value, kind) or (kind is str and not value):
        raise DefinitionError("%s: %s is missing required %r" % (source, what, key))
    return value
