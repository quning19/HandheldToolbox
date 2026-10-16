"""RetroLibX command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from retrolibx import __version__
from retrolibx.application import ConversionService
from frontend_devices.adb import (
    AdbReader, AdbUploader, capture_device, plan_device_upload,
)
from library_converter.handheld import HandheldConfig, build_handheld, scan_handheld
from library_converter.publication import AdbPublisher, plan_publication
from library_converter.deployment import DeploymentStage, deploy_task, plan_deployment
from retrolibx.core.models import Diagnostic, Library
from retrolibx.core.operations import ConversionPlan
from retrolibx.core.options import ConflictPolicy, ExportOptions, ImportOptions, MediaMode, RomMode
from retrolibx.errors import (
    ConflictError,
    DetectionError,
    ParseError,
    RetroLibXError,
    ValidationError,
)

app = typer.Typer(
    help="Universal Retro Game Library Converter",
    no_args_is_help=True,
    invoke_without_command=True,
)
console = Console()
error_console = Console(stderr=True)


def _json(value: object) -> None:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


def _library_table(library: Library) -> Table:
    table = Table(title=f"{library.format} library")
    table.add_column("System")
    table.add_column("Games", justify="right")
    table.add_column("Media", justify="right")
    for system in library.systems:
        table.add_row(
            Text(system.name),
            str(len(system.games)),
            str(sum(len(game.media.items()) for game in system.games)),
        )
    table.add_section()
    table.add_row("Total", str(library.game_count), str(library.media_count))
    return table


def _diagnostics(items: list[Diagnostic]) -> None:
    for item in items:
        style = (
            "red" if item.severity == "error" else "yellow" if item.severity == "warning" else "dim"
        )
        error_console.print(
            f"[{style}]{item.severity.upper()}[/{style}] {escape(item.code)}: {escape(item.message)}"
        )


def _plan_table(plan: ConversionPlan) -> Table:
    table = Table(title="Conversion plan")
    table.add_column("Operation")
    table.add_column("Count", justify="right")
    counts: dict[str, int] = {}
    for operation in plan.operations:
        key = operation.kind + (" (skipped)" if getattr(operation, "skipped", False) else "")
        counts[key] = counts.get(key, 0) + 1
    for key, value in sorted(counts.items()):
        table.add_row(key, str(value))
    return table


@app.callback()
def main(
    version: Annotated[bool | None, typer.Option("--version", help="Show version")] = None,
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
def detect(path: Path, json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    results = ConversionService().detect(path)
    if not results:
        raise DetectionError(f"Could not detect a supported library at {path}")
    if json_output:
        _json([result.model_dump(mode="json") for result in results])
        return
    table = Table(title="Detection results")
    table.add_column("Format")
    table.add_column("Confidence", justify="right")
    table.add_column("Evidence")
    for result in results:
        table.add_row(result.format, f"{result.confidence:.0%}", "; ".join(result.evidence))
    console.print(table)


@app.command()
def scan(
    path: Path | None = None,
    config: Annotated[Path | None, typer.Option("--config")] = None,
    source_format: Annotated[str | None, typer.Option("--from")] = None,
    source_profile: Annotated[Path | None, typer.Option("--source-profile")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    calculate_hashes: Annotated[bool, typer.Option("--hash")] = False,
    game_name_field: Annotated[
        str, typer.Option("--game-name-field", help="Source field used as the game name")
    ] = "label",
) -> None:
    if config is not None:
        if source_profile is not None:
            raise ValidationError("Set source_profile inside --config when using a configuration file")
        library = scan_handheld(HandheldConfig.load(config))
    elif path is not None:
        _, library = ConversionService().import_library(
            path,
            source_format,
            ImportOptions(
                calculate_hashes=calculate_hashes, game_name_field=game_name_field,
                source_profile=source_profile,
            ),
        )
    else:
        raise ValidationError("Provide a source path or --config")
    if json_output:
        _json(library)
    else:
        console.print(_library_table(library))
        _diagnostics(library.diagnostics)


@app.command()
def build(
    config: Annotated[Path, typer.Option("--config")],
    platforms: Annotated[list[str], typer.Option("--platform")],
    output: Annotated[Path, typer.Option("--out")],
) -> None:
    """Preview selected Pegasus platforms and build an offline Android task."""
    summary = build_handheld(HandheldConfig.load(config), platforms, output)
    _json(summary)
    if summary["errors"]:
        raise typer.Exit(4)


@app.command()
def capture(
    adb: Annotated[Path, typer.Option("--adb")],
    serial: Annotated[str, typer.Option("--serial")],
    source_root: Annotated[str, typer.Option("--source-root")],
    esde_root: Annotated[str, typer.Option("--esde-root")],
    platforms: Annotated[list[str], typer.Option("--platform")],
    output: Annotated[Path, typer.Option("--out")],
    systems_template: Annotated[Path | None, typer.Option("--systems-template")] = None,
) -> None:
    """Read selected metadata and indexes without downloading ROM or media contents."""
    _json(
        capture_device(
            AdbReader(adb, serial), source_root, platforms, esde_root, output, systems_template
        )
    )


@app.command()
def upload(
    source: Path,
    adb: Annotated[Path, typer.Option("--adb")],
    serial: Annotated[str, typer.Option("--serial")],
    remote: Annotated[str, typer.Option("--remote", help="Complete remote directory or filename")],
    apply: Annotated[bool, typer.Option("--apply", help="Perform the previewed upload")] = False,
) -> None:
    """Preview/upload one full directory via C2, or one file via C4."""
    if apply:
        _json(AdbUploader(adb, serial).upload(source, remote))
    else:
        _json({**plan_device_upload(source, remote), "serial": serial, "applied": False})


@app.command()
def publish(
    task: Path,
    adb: Annotated[Path, typer.Option("--adb")],
    serial: Annotated[str, typer.Option("--serial")],
    skip_platform_config: Annotated[bool, typer.Option("--skip-platform-config", help="Publish lists without replacing platform XML")] = False,
    apply: Annotated[bool, typer.Option("--apply", help="Publish the approved XML payloads via ADB")] = False,
) -> None:
    """Preview/publish metadata from this computer; does not execute the media script."""
    if apply:
        _json(AdbPublisher(adb, serial).publish(task, skip_platform_config))
    else:
        _json({**plan_publication(task, skip_platform_config), "serial": serial})


@app.command()
def deploy(
    task: Path,
    adb: Annotated[Path, typer.Option("--adb")],
    serial: Annotated[str, typer.Option("--serial")],
    remote: Annotated[str, typer.Option("--remote", help="Complete remote apply.sh filename")],
    stage: Annotated[DeploymentStage, typer.Option("--stage", help="Run only the selected approved stage, or all")] = DeploymentStage.ALL,
    skip_platform_config: Annotated[bool, typer.Option("--skip-platform-config")] = False,
    apply: Annotated[bool, typer.Option("--apply")] = False,
) -> None:
    """Preview/deploy a multi-platform task, recording stage timings locally."""
    if apply:
        _json(deploy_task(AdbPublisher(adb, serial), task, remote, stage, skip_platform_config))
    else:
        _json({**plan_deployment(task, remote, stage, skip_platform_config), "serial": serial})


@app.command("inspect")
def inspect_command(
    path: Path,
    source_format: Annotated[str | None, typer.Option("--from")] = None,
    source_profile: Annotated[Path | None, typer.Option("--source-profile")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    game_name_field: Annotated[
        str, typer.Option("--game-name-field", help="Source field used as the game name")
    ] = "label",
) -> None:
    _, library = ConversionService().import_library(
        path, source_format,
        ImportOptions(game_name_field=game_name_field, source_profile=source_profile),
    )
    if json_output:
        _json(library)
    else:
        console.print(_library_table(library))
        for system in library.systems:
            console.print(f"{system.name} ({system.id})", markup=False)
            for game in system.games:
                console.print(
                    f"  {game.name} — {len(game.roms)} ROM(s), {len(game.media.items())} media",
                    markup=False,
                )
        _diagnostics(library.diagnostics)


@app.command()
def validate(
    path: Path,
    source_format: Annotated[str | None, typer.Option("--from")] = None,
    source_profile: Annotated[Path | None, typer.Option("--source-profile")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    game_name_field: Annotated[
        str, typer.Option("--game-name-field", help="Source field used as the game name")
    ] = "label",
) -> None:
    _, library = ConversionService().import_library(
        path, source_format,
        ImportOptions(game_name_field=game_name_field, source_profile=source_profile),
    )
    if json_output:
        _json(library.diagnostics)
    else:
        _diagnostics(library.diagnostics)
        errors = sum(item.severity == "error" for item in library.diagnostics)
        console.print(
            f"Validation complete: {errors} error(s), {len(library.diagnostics) - errors} other diagnostic(s)"
        )
    if any(item.severity == "error" for item in library.diagnostics):
        raise typer.Exit(1)


@app.command()
def convert(
    source: Path,
    target_format: Annotated[str, typer.Option("--to")],
    output: Annotated[Path, typer.Option("--output")],
    source_format: Annotated[str | None, typer.Option("--from")] = None,
    platform_config_dir: Annotated[
        Path | None, typer.Option("--platform-config-dir", help="Complete shared platform XML directory")
    ] = None,
    source_profile: Annotated[Path | None, typer.Option("--source-profile")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    rom_mode: Annotated[RomMode, typer.Option("--rom-mode")] = RomMode.COPY,
    media_mode: Annotated[MediaMode, typer.Option("--media-mode")] = MediaMode.COPY,
    conflict: Annotated[ConflictPolicy, typer.Option("--conflict")] = ConflictPolicy.SKIP,
    in_place: Annotated[bool, typer.Option("--in-place")] = False,
    shared_pegasus: Annotated[bool, typer.Option("--shared-pegasus", help="Migrate media and patch original Pegasus metadata; requires --rom-mode none (default off)")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    game_name_field: Annotated[
        str, typer.Option("--game-name-field", help="Source field used as the game name")
    ] = "label",
) -> None:
    result = ConversionService(platform_config_dir=platform_config_dir).convert(
        source,
        output,
        target_format,
        source_format=source_format,
        import_options=ImportOptions(game_name_field=game_name_field, source_profile=source_profile),
        export_options=ExportOptions(
            rom_mode=rom_mode, media_mode=media_mode, conflict=conflict, in_place=in_place,
            shared_pegasus=shared_pegasus
        ),
        dry_run=dry_run,
    )
    if json_output:
        _json(result)
        return
    console.print(_library_table(result.library))
    console.print(_plan_table(result.plan))
    _diagnostics(result.plan.diagnostics)
    if dry_run:
        console.print("[bold]Dry run:[/bold] no files changed")
    elif result.execution:
        console.print(
            f"Completed {len(result.execution.completed)} operation(s); skipped {len(result.execution.skipped)}"
        )


def run() -> None:
    try:
        app()
    except (DetectionError, ParseError) as exc:
        error_console.print(f"[red]Error:[/red] {escape(str(exc))}")
        raise SystemExit(3) from exc
    except (ConflictError, ValidationError) as exc:
        error_console.print(f"[red]Error:[/red] {escape(str(exc))}")
        raise SystemExit(4) from exc
    except RetroLibXError as exc:
        error_console.print(f"[red]Error:[/red] {escape(str(exc))}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    run()
