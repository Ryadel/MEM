# node

- **kind**: runtime
- **capability**: run Node packages
- **min version**: 22 — v20 reached end of life on 2026-04-30, and v22 is in maintenance until 2027-04-30, per
  <https://raw.githubusercontent.com/nodejs/Release/main/schedule.json>. Raise to 24 before that date
- **purpose**: the runtime for `requires: node` entries. npm ships with it, and is what installs into the host's
  `node env`.
- **invocation**: `node <script>`; packages in the environment run from `<node env>/node_modules/.bin/<bin>`
- **licence**: MIT, verified 2026-10-05 against <https://raw.githubusercontent.com/nodejs/node/main/LICENSE>.
  Bundled dependencies carry their own licences
- **url**: https://nodejs.org

## Notes

- Probe with `node --version` and `npm --version`: a Node without npm cannot receive packages.
- The dedicated environment is a plain directory used as `npm --prefix <node env>`. npm then installs into
  `<node env>/node_modules` and links executables into `node_modules/.bin`
  (<https://docs.npmjs.com/cli/v11/configuring-npm/folders>); on Windows those are `.cmd` and `.ps1` shims.
- `npm install -g` is a **system** install, whatever the prefix: never the approved level.

## Alternatives

[python](python.md). Prefer a Python library when both ecosystems offer one, so a host needs one runtime rather
than two.
