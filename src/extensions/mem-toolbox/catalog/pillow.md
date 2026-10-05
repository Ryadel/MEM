# pillow

- **kind**: library
- **capability**: process images from code
- **requires**: python
- **package**: `pillow`
- **import**: `PIL`
- **min version**: 12.0 — needs Python 3.10 or newer
- **purpose**: image work inside a script — open, crop, resize, composite, draw text, convert — when the
  operation is one step of a larger program.
- **invocation**: `from PIL import Image`
- **licence**: MIT-CMU, verified 2026-10-05 against <https://raw.githubusercontent.com/python-pillow/Pillow/main/LICENSE>
- **url**: https://python-pillow.github.io

## Notes

- Imports as `PIL`, and cannot coexist with the original, abandoned `PIL` package.
- Wheels bundle the native codecs; nothing else needs installing on common platforms.
- It does not read SVG. Rasterise with [resvg](resvg.md) first.
- A dependency of [pdfplumber](pdfplumber.md) and [matplotlib](matplotlib.md), so often already present in the
  environment — probe before proposing.

## Alternatives

[imagemagick](imagemagick.md) or [vips](vips.md) when the job is a command over files rather than a step in a
program, and [vips](vips.md) at scale.
