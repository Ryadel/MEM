# Catalogue: capability → tool

Keyed by **capability**, because the lookup starts from a task and not from a tool name. Read this file to pick a
candidate, then read that tool's own page.

The catalogue is deliberately scoped to **media processing** — images, and since 1.0.1 audio and video: small and
opinionated, a default toolchain rather than an encyclopedia. Its value is preference and provenance — which tool
to reach for, and where it comes from — not explaining what well-known tools are.

Project entries in `custom/index.md` are read **first** and override these.

| Capability | Candidates |
|---|---|
| Convert or transform an image | [imagemagick](imagemagick.md), [vips](vips.md) |
| Resize or thumbnail, at scale | [vips](vips.md), [imagemagick](imagemagick.md) |
| Optimise a PNG losslessly | [oxipng](oxipng.md) |
| Render an SVG to a raster image | [resvg](resvg.md) |
| Upscale an image | [realesrgan](realesrgan.md) |
| Convert or transcode audio or video | [ffmpeg](ffmpeg.md) |
| Extract frames or stills from a video | [ffmpeg](ffmpeg.md) |
| Extract, replace or re-encode an audio track | [ffmpeg](ffmpeg.md) |
| Inspect media metadata, codecs and streams | [ffmpeg](ffmpeg.md) |

Being listed here says nothing about availability: check `custom/installed/<host>.md` before using one.

The id in the first column of a tool's page is also its folder name under the tools root — see "Where tools live
on disk" in the extension's `index.md`. Where a tool has more than one implementation, the id names the tool and
the implementation belongs to the build, not to the catalogue: `realesrgan`, not `realesrgan-ncnn-vulkan`.

Licences were read from upstream on the date recorded in each entry. Re-verify before relying on one: upstream
terms change, and a stale licence claim is worse than none. Note that for `ffmpeg` the licence of the **binary
build** can differ from the licence of the project — the entry explains why.
