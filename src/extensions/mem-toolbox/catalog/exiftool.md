# exiftool

- **kind**: cli
- **capability**: read or write image and media metadata
- **min version**: 13 — upstream publishes no support policy; 13.59 is current
- **purpose**: the reference reader and writer for EXIF, XMP, IPTC and maker notes, across images, video and PDF.
- **invocation**: `exiftool -json <file>` to read; `exiftool -overwrite_original -<tag>=<value> <file>` to write
- **licence**: Artistic-1.0-Perl OR GPL-1.0-or-later, verified 2026-10-05 against
  <https://raw.githubusercontent.com/exiftool/exiftool/master/README>
- **url**: https://exiftool.org

## Notes

- **Writing keeps a copy as `<file>_original`** unless `-overwrite_original` is passed. Decide which you want:
  that copy is the only undo.
- Windows: the archive holds `exiftool(-k).exe`, which **must** be renamed to `exiftool.exe` — `(-k)` makes it wait
  for a key press, which hangs a non-interactive call — and kept beside its `exiftool_files` folder. No Perl is
  needed there; elsewhere it needs Perl (<https://exiftool.org/install.html>).

## Alternatives

`ffprobe` from [ffmpeg](ffmpeg.md) for codecs and streams; exiftool for everything tagged.
