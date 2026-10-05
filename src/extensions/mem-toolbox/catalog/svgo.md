# svgo

- **kind**: library
- **capability**: optimise an SVG
- **requires**: node
- **package**: `svgo`
- **min version**: 4.0
- **purpose**: shrink SVGs by removing editor metadata, collapsing groups and shortening paths — the standard
  step before shipping a hand-exported SVG.
- **invocation**: `<node env>/node_modules/.bin/svgo <in.svg> -o <out.svg>`
- **licence**: MIT, verified 2026-10-05 against <https://raw.githubusercontent.com/svg/svgo/main/LICENSE>
- **url**: https://svgo.dev

## Notes

- A library in this catalogue's terms — it is installed into the `node env` — used through its CLI.
- The default preset rewrites `id` attributes. An SVG styled or scripted by id from outside **must** be checked
  after optimisation, or optimised with that plugin disabled.
- 4.x is ESM-only, and its configuration and plugin API differ from 3.x.

## Alternatives

None for optimisation. [resvg](resvg.md) renders an SVG; it does not optimise one.
