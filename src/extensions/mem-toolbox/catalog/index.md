# Catalogue: capability → tool

Keyed by **capability**, because the lookup starts from a task and not from a tool name. Read this file, then the
sub-index for the task's domain to pick a candidate, then that tool's own page.

The catalogue covers **media, documents and data** — since 1.0.2 it holds libraries and the runtimes they need
as well as CLI tools. It stays opinionated: a default toolchain, not an encyclopedia. Its value is preference and
provenance — which tool to reach for, and where it comes from — not explaining what well-known tools are.

Project entries in `custom/index.md` are read **first** and override these.

## Runtimes

A library is only usable through its runtime. Probe the runtime first; see "Libraries and runtimes" in the
extension's `index.md`.

| Capability | Candidates |
|---|---|
| Run Python libraries | [python](python.md) |
| Run Node packages | [node](node.md) |

## Domains

| Domain | Sub-index | Covers |
|---|---|---|
| Media | [index.media.md](index.media.md) | images, SVG, metadata, audio and video |
| Documents | [index.documents.md](index.documents.md) | PDF, Word, Excel, PowerPoint, document conversion |
| Data | [index.data.md](index.data.md) | CSV and tabular data, JSON, charts |

A candidate list may mix CLI tools and libraries. They compete in one list, in preference order: a library is
not a fallback for a CLI tool, nor the reverse.

## Reading an entry

Being listed here says nothing about availability: check `custom/installed/<host>.md` before using one.

The id is the entry's filename and, for a CLI tool, its folder name under the tools root — see "Where tools live
on disk" in the extension's `index.md`. Where a tool has more than one implementation, the id names the tool and
the implementation belongs to the build: `realesrgan`, not `realesrgan-ncnn-vulkan`. A library has no folder: it
lives in an agent environment.

Licences were read from upstream on the date recorded in each entry. Re-verify before relying on one: upstream
terms change, and a stale licence claim is worse than none. For `ffmpeg` the licence of the **binary build** can
differ from the project's, and for `reportlab` only the open-source toolkit is covered; both entries explain.

Deliberately absent: PyMuPDF and Ghostscript, both AGPL-3.0, verified 2026-10-05. A project may still add either
as a custom entry, knowing the licence.
