# Changelog

All notable changes to RetroLibX will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Preview-first `deploy` reuses C4 upload and host publication for one multi-platform
  task; explicit upload/copy/publish stages record local timings and failures.
  Resource audits and repairs remain separate from execution. No tests or device
  deployment were run for this refactor.
- Explicit metadata Android launch conversion and reusable system-template mappings
  replace task-specific launch parsers and cloned XML files. Existing node positions
  and ROM-path spelling are preserved; task payload construction and publication
  previews reuse one representation instead of loading or generating it twice.

- Explicit legacy gamelist system IDs and ROM-root mappings preserve user metadata
  when Android platform names or source directories change, without treating a
  borrowed list as the baseline of a nonexistent new target.

- Minimal Android media scripts use mkdir and cp only. Computer-side `publish`
  backs up and publishes gamelists/configuration through ADB C4, with optional
  platform-config exclusion. Shared source-media verification and cleanup remain
  on the computer-side publication path; ordinary copy avoids repeated media checks.

- Preview-first Android `upload` command: C2 copies complete directory contents
  into an explicitly created target; C4 copies one file to its full remote filename.
  Unicode argument lists avoid implicit source-basename handling on Windows ADB.
  Selected-file operations remain file-oriented; remote extras are not deleted.

- Opt-in shared cover, logo and video migration, disabled by default. Verified
  target copies precede byte-preserving asset patches to original Pegasus metadata;
  source-media cleanup follows publication, retaining mini and other referenced assets.
  Local dry-run and Android task generation leave inputs untouched.

- Explicit generic and Pegasus G source profiles for media fallbacks, version-note
  normalization and per-platform Android launch confirmation. Raw source fields
  remain in the IR; ordinary Pegasus imports no longer assume Pegasus G conventions.

- Shared platform configuration and recognition extracted from the tested theme
  converter: 76 system definitions, exact names and directories, and shared theme
  batch defaults. Internal platforms now use `GBA HACK` and `GBA vib`.
- Scoped Android `build` and batch `capture` commands, offline task previews,
  minimal device media copies, configuration baselines and backups.
- Independent GBA hack and GBA vib entries; the Pegasus G source profile requires
  launch confirmation for GBA vib before an executable task is emitted.
- ES-DE gamelist merging preserving user fields, extra records, existing system IDs
  and absolute custom media-directory settings.
- Explicit target system identifiers and native ES-DE settings fragment support;
  captured settings remain unchanged and are guarded by their original digest.

### Fixed

- Restrict ES-DE media exports and bundled Pegasus G fallbacks to covers, logos
  and videos; remove the five additional export roles and their new aliases.
  Keep upstream generic media fields intact. The 15 scoped local media cases have
  passing results across the initial run and targeted failure retests; no device
  execution or full regression was performed.
- Recognize the first ROM variant's already-migrated asset for every variant when
  regenerating a shared-media plan, without treating that asset as an escaped source.

- VIB confirmation retains verified command alternatives and no longer requires a
  fixed core filename or a launch override. ES-DE export consumes normalized game
  fields rather than guessing version notes from Pegasus developer values.

- Both local ES-DE conversion and Android tasks merge existing gamelists with the
  same preserving policy, baseline guards and backups; dry-run remains read-only.
- Shared platform fields are read from the verified XML configuration instead of
  duplicated JSON definitions. Theme conversion uses its configured XML baseline;
  explicit complete configuration directories are supported by build and convert.

- Android task exports retain the complete platform configuration and companion
  discovery/import/sorting rules regardless of selected game platforms. Blocked
  launch mappings still produce complete configuration previews without apply.sh.
- Preserve parentheses in platform recognition, so `MD hack` and
  `MD hack(picodrive)` remain distinct; output aliases do not alter internal identity.
- Pegasus handles `files`, blank lines, comments, inherited launch commands,
  strict explicit encodings, platform boundaries and game-local media fallbacks.
- ES-DE expands shared media per ROM and retains subdirectories in the proper
  downloaded_media/gamelists layout; duplicate destinations are rejected.
- Pegasus exports preserve unrecognized source values and nested ROM/media paths.
- Local copies use temporary files; guarded configuration writes retain backups
  and reject external changes. CLI business failures no longer print tracebacks.

## [0.1.0] - 2026-08-27

### Added

- Introduced the typed RetroLibX intermediate representation (RLX IR) for libraries, systems,
  games, multi-file ROMs, semantic media, collections, launch configuration, and diagnostics.
- Added detection, import, and export support for RetroArch, generic EmulationStation, ROCKNIX,
  ES-DE, and Pegasus libraries.
- Added the `detect`, `scan`, `convert`, `inspect`, and `validate` CLI commands with Rich output
  and machine-readable JSON modes.
- Added a versioned canonical system registry for platform aliases, ROM extensions, playlist
  names, target directories, and Pegasus short names.
- Added recursive discovery for `.lpl`, `gamelist.xml`, and `metadata.pegasus.txt` files across
  repositories with non-standard directory layouts.
- Added repository-wide ROM and media resolution using direct paths, metadata-relative paths,
  repository-relative paths, trailing-path matching, and unambiguous filename fallback.
- Added `--game-name-field` to read game titles from non-standard RetroArch playlist fields while
  retaining the original `label` for thumbnail matching.
- Added conversion planning with dry-run reports, conflict policies (`skip`, `overwrite`,
  `rename`, `error`, and `newer`), and configurable ROM and media transfer modes.
- Added versioned `.retrolibx/manifest.json` output containing conversion provenance and selected
  file policies.
- Added adapter capability declarations and data-loss diagnostics when a target format cannot
  represent source metadata.
- Added opt-in CRC32, MD5, and SHA-1 ROM hashing with `scan --hash`.
- Added unit, adapter, round-trip, safety, CLI, and end-to-end tests with an 80% coverage gate.
- Added GitHub Actions checks for pytest, Ruff, formatting, strict mypy, and package builds.
- Added trusted PyPI publishing for matching `v*` tags, including tag/package version validation.
- Added project artwork, repository guidance for coding agents, and MIT licensing.

### Changed

- Separated format adapters from platform profiles so ROCKNIX and ES-DE can reuse
  EmulationStation XML primitives without inheriting platform-specific behavior.
- Separated adapter rendering, conversion planning, and filesystem execution so adapters remain
  side-effect free and dry-run never writes target files.
- Standardized resolved IR paths as absolute `Path` values without requiring source metadata to
  use absolute or currently valid device paths.
- Made metadata writers deterministic through stable system, game, field, and path ordering.

### Fixed

- Fixed RetroArch detection when `retroarch/playlists` is nested below a game collection root.
- Fixed ROM lookup for playlists containing stale device paths such as `/storage/roms/...` or
  `/ROM/...` when the files exist elsewhere in the supplied repository.
- Fixed thumbnail lookup for repositories that store artwork outside the conventional RetroArch
  directory while preserving semantic distinctions between box art, screenshots, and titles.
- Fixed Hatch package configuration so wheel and source distributions include the complete Python
  package as well as the system registry and license.

### Security

- Kept source libraries read-only by default and rejected source/target path equality unless
  explicitly allowed.
- Constrained every planned and executed destination to the selected target root and rechecked
  filesystem state immediately before writes.
- Disabled XML network access, DTD loading, and external entity resolution.
- Used atomic metadata writes and wrote the RetroLibX manifest only after preceding operations
  completed.
- Treated imported launch commands as metadata only; RetroLibX never executes them.

[Unreleased]: https://github.com/tiancheng91/RetroLibX/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tiancheng91/RetroLibX/releases/tag/v0.1.0

