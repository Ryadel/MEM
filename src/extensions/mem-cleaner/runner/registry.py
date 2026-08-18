"""Loads provider definitions and resolves capabilities to providers.

This module and pipeline.py are the engine. Neither contains a provider id:
resolution happens through the tables built here, from data on disk. That is a
testable property -- grep this package for a provider name and find nothing.

Precedence is base wins, the opposite of mem-toolbox, because what is being
overridden here is executable behaviour rather than reference data. A custom
definition reusing a distributed id is refused, not resolved.
"""

from __future__ import annotations

import os

from . import frontmatter
from .models import DefinitionError, Provider


class RegistryError(ValueError):
    """The set of definitions on disk is inconsistent."""


class Registry:
    def __init__(self, providers, problems):
        self._providers = {p.id: p for p in providers}
        self.problems = problems

    def __len__(self):
        return len(self._providers)

    def all(self):
        return [self._providers[key] for key in sorted(self._providers)]

    def get(self, provider_id):
        return self._providers.get(provider_id)

    def resolve(self, capability, role, pinned=None):
        """Return candidate (provider, operation) pairs, best first.

        A pin restricts the search to one provider and fails loudly when that
        provider cannot do the job, rather than quietly falling back.
        """
        if pinned is not None:
            provider = self._providers.get(pinned)
            if provider is None:
                return []
            return [(provider, op) for op in provider.find(capability, role)]

        candidates = []
        for provider in self.all():
            for operation in provider.find(capability, role):
                candidates.append((provider, operation))
        # Distributed definitions before custom ones: base wins.
        candidates.sort(key=lambda pair: (pair[0].is_custom, pair[0].id))
        return candidates


def load(extension_root):
    """Load base and custom provider definitions under an extension root."""
    providers = []
    problems = []
    seen = {}

    for directory, is_custom in (
        (os.path.join(extension_root, "providers"), False),
        (os.path.join(extension_root, "custom", "providers"), True),
    ):
        for path in _definition_files(directory):
            try:
                provider = _load_one(path)
            except (DefinitionError, frontmatter.FrontMatterError) as error:
                problems.append(str(error))
                continue

            if is_custom and not provider.is_custom:
                problems.append(
                    "%s: a custom provider id must be namespaced 'custom/<id>'" % path
                )
                continue
            if not is_custom and provider.is_custom:
                problems.append(
                    "%s: a distributed provider id must not use the custom/ namespace" % path
                )
                continue

            if provider.id in seen:
                # Base wins, and the collision is reported rather than resolved.
                problems.append(
                    "%s: id %r already defined by %s; collisions are refused"
                    % (path, provider.id, seen[provider.id])
                )
                continue

            seen[provider.id] = path
            providers.append(provider)

    return Registry(providers, problems)


def _definition_files(directory):
    if not os.path.isdir(directory):
        return []
    names = sorted(
        name
        for name in os.listdir(directory)
        if name.endswith(".md") and name != "index.md" and not name.startswith("_")
    )
    return [os.path.join(directory, name) for name in names]


def _load_one(path):
    with open(path, "r", encoding="utf-8") as handle:
        data, _ = frontmatter.load(handle.read())
    if not data:
        raise DefinitionError("%s: no front matter" % path)
    return Provider(data, path)
