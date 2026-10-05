# matplotlib

- **kind**: library
- **capability**: plot a chart to an image
- **requires**: python
- **package**: `matplotlib`
- **min version**: 3.10
- **purpose**: static charts written to PNG, SVG or PDF from a script.
- **invocation**: `import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt`
- **licence**: a PSF-style licence of its own ("License agreement for matplotlib versions 1.3.0 and later"), with
  no SPDX identifier declared upstream, verified 2026-10-05 against
  <https://raw.githubusercontent.com/matplotlib/matplotlib/main/LICENSE/LICENSE>
- **url**: https://matplotlib.org

## Notes

- Select the `Agg` backend before importing `pyplot` when there is no display; otherwise a headless run fails or
  tries to open a window.
- Heavy: it pulls numpy and [pillow](pillow.md).
- `savefig(..., bbox_inches="tight")` keeps labels from being cut off.

## Alternatives

None in this catalogue.
