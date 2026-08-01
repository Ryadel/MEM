# vips

- **kind**: cli
- **capability**: resize or thumbnail, at scale; convert or transform an image
- **purpose**: fast, low-memory image processing. The preferred choice for resizing and thumbnailing in bulk,
  where its streaming model avoids loading whole images into memory.
- **invocation**: `vips <operation> <input> <output> [options]`; `vipsthumbnail <input> -s <size>`
- **licence**: LGPL-2.1-or-later, verified 2026-08-01 against the upstream repository
- **url**: https://www.libvips.org

## Notes

- `vipsthumbnail` is the dedicated entry point for resizing and is usually the right one, rather than a generic
  `vips resize`.
- The licence is LGPL: linking the library into a distributed product has obligations that invoking the CLI does
  not. Record `kind` accurately when a project uses the library rather than the binary.
- On Windows it commonly ships as an extracted archive rather than an installer, so the path is project-specific
  and belongs in the host entry.

## Alternatives

[imagemagick](imagemagick.md) covers more formats and operations. Prefer it when breadth matters more than speed.
