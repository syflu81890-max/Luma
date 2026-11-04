# Video-poster hotfix validation

2026-11-04, Windows x64. Builds and integration tests use isolated test profiles.

- The synthetic portrait H.264 regression reproduced corrupted scanlines before the fix; the same content passes after selecting portable CPU code.
- Picture-content assertions cover H.264 color/pattern accuracy, regeneration of old corrupt posters for videos and MP4-backed GIFs, reuse of regenerated posters, preservation of original bytes and notes, and removal of both cache generations when test media is purged.
- Frozen-backend verification also measures the H.264 poster against the synthetic source pattern, rather than accepting a successful process exit or JPEG header.
- This change does not alter database schema, source media, X capture boundaries or session configuration. Existing beta.1 validation and known limits continue to apply.
