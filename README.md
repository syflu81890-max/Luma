# Luma

A local-first Windows library for collecting, finding and organizing photos, videos and GIFs from X. English and Simplified Chinese interfaces.

[简体中文](README.zh-CN.md) · [Downloads](https://github.com/syflu81890-max/Luma/releases) · [Report a bug](https://github.com/syflu81890-max/Luma/issues/new/choose)

**0.5.1-beta.2 — public beta, Windows 10/11 x64.** Download the portable EXE to run without installation, or use the Setup EXE. Windows builds are currently unsigned. Source archives and SHA-256 checksums accompany releases.

## What it does

- Collect authorized X media with original post text, publication dates and source links. Preview tasks, download incrementally, schedule updates, and retain exclusions for deleted items.
- Browse accounts with pinned avatars, nickname/avatar history, private aliases, quick notes, ratings, editable region flags and up to three collections. Reorder collections by dragging.
- Organize media with albums, tags, saved filters, date/type/account filters, drag selection, sticky bulk actions and a recoverable Trash.
- Find similar images with remembered results, incremental or scoped scans, ignored groups and a reviewed plan to keep higher-resolution copies. Favorites and AI versions receive extra protection.
- Search locally with optional Chinese-CLIP semantic search and OCR. Models download separately; inference stays on your PC.
- Switch independent library spaces, preserve account/task records, export files, and use an opt-in authenticated loopback assistant API for external tools.
- Use your own logged-in X session for accessible private accounts; browser capture is available when the normal collector cannot read them.

## Start and upgrade

1. Run Luma and choose a library location. Keep originals and the database together.
2. Sign in to X in Luma's login window and add an account or supported URL. First collector use downloads about 1.4 MB of pinned, hash-verified components from official PyPI hosting. Subsequent use relies on the local cache.
3. Review a small capture before starting a larger task. X access, session validity and rate limits affect results.

Before upgrading, fully quit the older application and back up the library. Schema upgrades create a database backup, but a complete backup should also include media. This beta addresses library-switch hangs with an observable, cancellable transition; a failed switch preserves the old library selection.

## Current limits

Real-account following imports and private-account capture need broader live testing. Video playback depends on Chromium codec support; unsupported encodings may still import with a cover image and require an external player. Language-based region suggestions are editable hints, not verified nationality. Similarity and OCR can make mistakes: review removal plans. Automatic nudity classification, NAS/server mode, cloud backup and graphical theme packs are not included. Theme extension interfaces are documented for later work.

No telemetry or cloud inference is enabled. Credentials, databases, collected media and model caches are excluded from the public source. The optional assistant API binds to loopback, requires a token and is off by default. See [Privacy](docs/PRIVACY.md).

## Contribute and build

Ideas and bug reports in English or Chinese are welcome. Please include the version and reproducible steps using sample data; remove credentials and private paths. See [Contributing](CONTRIBUTING.md), [Build instructions](docs/BUILDING.md), [Translation guide](docs/TRANSLATING.md), and [release notes](docs/RELEASE_NOTES_0.5.1-beta.2.md).

Luma core: **GPL-3.0-or-later**. Independent collector integration: **GPL-2.0-only**. Third-party components and model data retain their original licenses. User media is outside this license grant. See [COPYRIGHT](COPYRIGHT), [third-party notices](THIRD_PARTY_NOTICES.md) and [corresponding source](docs/SOURCE_CODE.md).
