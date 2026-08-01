# realesrgan-ncnn-vulkan

- **kind**: cli
- **capability**: upscale an image
- **purpose**: neural upscaling and restoration, at 2x, 3x or 4x. Reach for it when an asset only exists at low
  resolution and a conventional resize is not good enough.
- **invocation**: `realesrgan-ncnn-vulkan -i <input> -o <output> -s <scale> [-n <model>]`
- **licence**: MIT, verified 2026-08-01 against the upstream repository. The bundled models and the ncnn runtime
  carry their own terms — check them before redistributing
- **url**: https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan

## Notes

- Requires a working Vulkan driver. Absence of one is a runtime failure rather than a missing binary, so record
  it as `unavailable` on that host with the reason.
- Output is **generated detail**, not recovered detail. Never use it where the image is evidence, or where
  fidelity to the original matters.
- Several models ship with it, tuned for different content; the default is not always the right one.
- Ships as an extracted archive rather than an installer, so the path is host-specific.

## Alternatives

For ordinary enlargement without invention, [vips](vips.md) or [imagemagick](imagemagick.md) are the correct
tools and far cheaper.
