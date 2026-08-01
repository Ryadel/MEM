# resvg

- **kind**: cli
- **capability**: render an SVG to a raster image
- **purpose**: turn static SVG into PNG. A small standalone binary with no external dependencies, which makes it
  a good fit where a browser-based renderer would be disproportionate.
- **invocation**: `resvg <input.svg> <output.png> [--width N]`
- **licence**: Apache-2.0 OR MIT, verified 2026-08-01 against the upstream repository
- **url**: https://github.com/linebender/resvg

## Notes

- Scope is **static** SVG: no scripting, and animation is not rendered. An SVG that depends on either will render
  wrong rather than fail loudly, so check the source before trusting the output.
- Fonts are resolved from the system, so the same file can render differently across hosts. Pin or embed fonts
  when the output must be reproducible.

## Alternatives

[imagemagick](imagemagick.md) can rasterise SVG, but usually by delegating to another renderer, so the result
depends on the build. Prefer resvg when the output must be predictable.
