# imagemagick

- **kind**: cli
- **capability**: convert or transform an image; resize or thumbnail
- **purpose**: general-purpose image conversion and manipulation. The broadest format coverage of the tools here,
  and the default choice when the operation is unusual or the format is uncommon.
- **invocation**: `magick <input> [options] <output>`
- **licence**: ImageMagick License, verified 2026-08-01 against the repository `LICENSE` file. Upstream declares
  no SPDX identifier there and states the terms are compatible with GPL v3
- **url**: https://imagemagick.org/

## Notes

- Version 7 exposes a single `magick` entry point. Older installations use per-operation binaries such as
  `convert`, which on Windows collides with the system `convert.exe` — prefer `magick` and record the version.
- Delegate libraries are optional and vary by build, so format support differs between installations. Check the
  build rather than assuming.

## Alternatives

[vips](vips.md) is markedly faster and uses far less memory on large images and on batch resizing. Prefer vips
when throughput matters; prefer ImageMagick for breadth of formats and operations.
