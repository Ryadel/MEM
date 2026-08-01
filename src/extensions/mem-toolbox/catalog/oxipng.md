# oxipng

- **kind**: cli
- **capability**: optimise a PNG losslessly
- **purpose**: reduce PNG size without changing the image. Multithreaded, and a safe final step in an asset
  pipeline because the output is pixel-identical.
- **invocation**: `oxipng -o <level> <file>`
- **licence**: MIT, verified 2026-08-01 against the upstream repository
- **url**: https://github.com/oxipng/oxipng

## Notes

- Optimisation levels run 0 to 6; higher levels cost time for diminishing returns.
- It rewrites files **in place** by default. That is a mutation, so treat a bulk run as a destructive operation
  and confirm it, even though the pixels are preserved.
- Metadata stripping is opt-in. Do not enable it silently: it can remove colour profiles and attribution.

## Alternatives

A Rust rewrite of OptiPNG, which it supersedes for most uses. It optimises PNG only — for other formats use
[imagemagick](imagemagick.md) or [vips](vips.md).
