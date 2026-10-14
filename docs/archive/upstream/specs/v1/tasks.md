# RetroLibX V1 Implementation Plan

## Pegasus G / Android extension

- [x] Extract tested theme platform definitions and recognition; connect both tools.
- [x] Replace gbah/gbavib internal identities with GBA HACK/GBA vib and retain ROM/theme names.
- [x] Read-only compare all four platform XML files with RP6; preserve the complete configuration independently of game selection.
- [ ] Run any further tests only after explicit user approval; default to static review.
- [x] Repair file/files parsing, media fallback and selected-platform boundaries.
- [x] Generate per-ROM ES-DE media and lists with subdirectories and collision checks.
- [x] Preserve existing metadata, system IDs, themes and commands; guard and back up XML.
- [x] Add batch Android capture and an offline script from the same ConversionPlan.
- [x] Verify real 12/36, 15/45 and full-library 503/1509 mappings.
- [x] Verify MuMu copy/hash, rerun, external config changes and interrupted copies.
- [ ] Validate ES-DE display, emulator launch, VIB rumble and manual terminal permissions.

- [x] 1. Bootstrap the Python project
  - Add `pyproject.toml`, package metadata, CLI entry point, dependency and tool configuration.
  - Create the source/test directory structure and basic documentation.
  - _Requirements: 1, 9_

- [x] 2. Implement the domain and diagnostic foundation
  - Implement RLX IR, options, capabilities, diagnostics, errors, serialization, and normalization.
  - Implement the versioned canonical system registry and packaged YAML data.
  - _Requirements: 2, 3, 4_

- [x] 3. Implement planning and safe execution
  - Implement export intents, typed operations, conflict handling, containment checks, dry-run plans, executor, and manifest.
  - Cover ROM/media modes and source-safety invariants; legacy symbolic-link export is excluded from project tests and coverage by user request.
  - _Requirements: 8_

- [x] 4. Implement RetroArch and ROCKNIX vertical slice
  - Implement RetroArch detection, playlist/media import and export.
  - Implement reusable EmulationStation XML primitives and ROCKNIX profile/adapter.
  - Add MVP integration fixtures and tests.
  - _Requirements: 4, 5, 6, 10_

- [x] 5. Implement remaining V1 adapters
  - Implement generic EmulationStation, ES-DE, and Pegasus detection/import/export/media rules.
  - Add adapter contract, golden, and semantic round-trip tests.
  - _Requirements: 4, 6, 7, 10_

- [x] 6. Implement the application service and CLI
  - Implement detect, scan, convert, inspect, and validate workflows.
  - Add Rich human output, JSON output, aliases, stable errors, and data-loss reporting.
  - _Requirements: 4, 8, 9_

- [x] 7. Complete verification and documentation
  - Run and fix pytest with coverage, Ruff formatting/linting, and strict mypy.
  - Verify dry-run, source safety, conflicts, format round trips, and end-to-end conversion.
  - Complete README usage and extension documentation.
  - _Requirements: 1, 10_
