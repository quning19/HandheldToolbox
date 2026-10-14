<p align="center">
  <img src="https://raw.githubusercontent.com/tiancheng91/RetroLibX/main/assets/repo-card.png" alt="RetroLibX — Universal Retro Game Library Converter" width="100%">
</p>

<p align="center">
  <a href="https://github.com/tiancheng91/RetroLibX/actions/workflows/ci.yml"><img src="https://github.com/tiancheng91/RetroLibX/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/tiancheng91/RetroLibX/actions/workflows/publish.yml"><img src="https://github.com/tiancheng91/RetroLibX/actions/workflows/publish.yml/badge.svg" alt="Publish"></a>
  <a href="https://pypi.org/project/retrolibx/"><img src="https://img.shields.io/pypi/v/retrolibx?label=pypi&color=blue" alt="PyPI version"></a>
  <a href="https://pypi.org/project/retrolibx/"><img src="https://img.shields.io/pypi/pyversions/retrolibx" alt="Python versions"></a>
  <a href="https://github.com/tiancheng91/RetroLibX/blob/main/LICENSE"><img src="https://img.shields.io/pypi/l/retrolibx" alt="License"></a>
</p>

---

# RetroLibX

This checkout extends upstream commit `f1a73c126ba450ae7d01a856e17ed7aad83eeff9`
for Pegasus G libraries and Android ES-DE tasks. See [Android usage](../../ANDROID.md)
for selected-platform scans, task generation and batch device capture. The existing
IR, adapters, planner, executor and upstream commands remain available.

当前模型、平台定义、目录结构及数据保留边界见
[项目说明](../../PROJECT_GUIDE.md)；配置与硬编码问题见
[2026-10-12 静态 review](../../REVIEW-2026-10-12.md)。

天马媒体、版本说明及 VIB 确认使用明确的
[来源规则](../../SOURCE_PROFILES.md)，普通 Pegasus 与天马G分别配置。

**Universal Retro Game Library Converter**

RetroLibX migrates ROM references, metadata, artwork, videos, collections, and launch settings between RetroArch, generic EmulationStation, ROCKNIX, ES-DE, and Pegasus. All conversions pass through a typed, platform-neutral intermediate representation rather than point-to-point converters.

## Quick Start

Run RetroLibX directly with [uv](https://docs.astral.sh/uv/) without installing it:

```bash
uvx retrolibx --help
```

Convert a RetroArch library to ROCKNIX:

```bash
uvx retrolibx convert /path/to/retroarch \
  --to rocknix \
  --output /path/to/rocknix
```

Preview the conversion without writing any files:

```bash
uvx retrolibx convert /path/to/retroarch \
  --to rocknix \
  --output /path/to/rocknix \
  --dry-run
```

For a non-standard RetroArch playlist whose title is stored in another field, select it
explicitly. The original `label` is still used to match thumbnails:

```bash
uvx retrolibx scan /path/to/library --game-name-field core_name
uvx retrolibx convert /path/to/library --to rocknix --output /path/to/target \
  --game-name-field core_name
```

The source is read-only by default. ROM modes are `copy`, `move`, `symlink` (`link` alias), `hardlink`, and `none`; media modes are `copy`, `symlink`, and `hardlink`. Conflict policies are `skip`, `overwrite`, `rename`, `error`, and `newer`.

## Commands

- `detect`: rank supported source formats.
- `scan`: import and summarize a library; `--json` outputs RLX IR and `--hash` calculates ROM hashes.
- `convert`: plan and execute a conversion; `--dry-run` never writes.
- `inspect`: show systems, games, ROMs, and media.
- `validate`: report broken paths, unknown systems, duplicates, and malformed metadata.

Aliases: `ra` → `retroarch`, `es` → `emulationstation`, `esde` → `es-de`.

## Repository discovery

RetroLibX does not require one fixed repository layout. It recursively discovers `.lpl`,
`gamelist.xml`, and `metadata.pegasus.txt` below the supplied source root (excluding tool and
VCS directories). Referenced ROM and media paths are resolved in this order:

1. an existing absolute path;
2. a path relative to the metadata file or detected frontend root;
3. a path relative to the supplied repository root;
4. a unique trailing-path match, which handles stale device roots such as `/storage/roms`;
5. a unique filename match, with semantic directory hints for ROMs, covers, screenshots,
   videos, and manuals.

Ambiguous filename matches are intentionally left unresolved and reported by validation instead
of silently selecting the wrong game or artwork.

## Development

```bash
uv run pytest --cov
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Architecture and acceptance criteria are documented in [`specs/v1`](specs/v1). Adapters implement detection/import/render only. Rendering returns an `ExportIntent`; the planner resolves all conflicts and paths; the executor is the sole filesystem writer.

## License

RetroLibX is released under the [MIT License](../../../LICENSE).
