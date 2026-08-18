# ffmpeg

- **kind**: cli
- **capability**: convert or transcode audio or video; extract frames or stills from a video; extract, replace
  or re-encode an audio track; inspect media metadata, codecs and streams
- **purpose**: the default answer for anything involving a media container or codec. Reach for it whenever the
  task names a video or audio file — the image tools here do not read containers at all.
- **invocation**: `ffmpeg -i <input> [options] <output>`, and `ffprobe -v error -print_format json -show_streams
  <input>` for inspection
- **licence**: **read the two separately.** The *project* is LGPL-2.1-or-later, and GPL-2.0-or-later once its
  optional GPL components are compiled in — "If those parts get used the GPL applies to all of FFmpeg", verified
  2026-08-17 against <https://ffmpeg.org/legal.html>. A *binary build* therefore carries whatever its builder
  chose: the gyan.dev Windows builds state "All builds are 64-bit, static and licensed as GPLv3", verified
  2026-08-17, and ship a GPL v3 `LICENSE` file. Record the licence of the build actually installed, not the
  project's default
- **url**: https://ffmpeg.org/

## Notes

- Ships as three executables: `ffmpeg` (convert), `ffprobe` (inspect), `ffplay` (play). Use `ffprobe` for any
  question about a file — invoking `ffmpeg` to find out what something is will also start work on it.
- **`ffmpeg` prompts before overwriting an existing output.** With no interactive terminal that prompt has
  nowhere to go, and the process appears to hang. Always pass `-y` (overwrite) or `-n` (never overwrite); the
  choice is deliberate, because `-y` on the wrong path destroys the original.
- `-c copy` remuxes without re-encoding: near-instant, lossless, and the right default when only the container
  changes. Re-encoding a file that only needed a remux is the most common way to lose quality here.
- `-v error -hide_banner` makes output parseable; the default log level buries errors under a build banner.
- Codec availability depends on how the build was configured, not on the version. Probe with
  `ffmpeg -hide_banner -encoders` rather than assuming a codec is present.
- The GPL question is about **distribution**, not use: invoking a GPL binary as a separate process does not
  affect your own project's licensing. Bundling or linking it does. This is exactly the distinction the `kind`
  field exists to preserve — see `TOOL.template.md`.

## Alternatives

None here, and that is the point: no other tool in this catalogue reads a media container. For **still images**
the reverse holds — ffmpeg can convert them, but [imagemagick](imagemagick.md) and [vips](vips.md) are better at
it and far lighter. Use ffmpeg for images only when they are frames of something.
