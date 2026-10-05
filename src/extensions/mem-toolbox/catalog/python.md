# python

- **kind**: runtime
- **capability**: run Python libraries
- **min version**: 3.11 — 3.10 reached end of life on 2026-10-01, per <https://peps.python.org/api/release-cycle.json>
- **purpose**: the runtime every `requires: python` entry runs on. Reach for it through the host's `python env`,
  never through whichever `python` happens to be first on `PATH`.
- **invocation**: `<python env>/bin/python <script>`, or `<python env>\Scripts\python.exe <script>` on Windows
- **licence**: PSF-2.0, verified 2026-10-05 against <https://raw.githubusercontent.com/python/cpython/main/LICENSE>
- **url**: https://www.python.org

## Notes

- Probe with `python --version`. On Windows, a `python` that opens the Microsoft Store instead of answering is
  the app-execution alias, not an interpreter: record `unavailable`.
- A venv is bound to the `X.Y` that created it. After an interpreter upgrade the old environment works with the
  old interpreter only; a new `X.Y` gets a sibling `envs/python-<X.Y>/`.
- Debian 12 and later, Ubuntu and Homebrew mark their system Python as externally managed
  ([PEP 668](https://peps.python.org/pep-0668/)): `pip install` outside a venv is refused. On those hosts
  `python env: system` cannot receive packages without a flag that defeats the protection — say so when the
  environment question is asked.
- The probe for libraries is in `index.md`, "Libraries and runtimes".

## Alternatives

[node](node.md), for libraries that exist only on npm.
