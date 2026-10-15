"""The only component authorized to apply a ConversionPlan."""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from retrolibx.errors import FileOperationError

from .operations import (
    ConversionPlan,
    CreateDirectory,
    ExecutionReport,
    MigrateSourceMedia,
    TransferFile,
    WriteManifest,
    WriteSourceMetadata,
    WriteText,
)
from .media import file_digest
from .options import MediaMode, RomMode


class PlanExecutor:
    def execute(self, plan: ConversionPlan) -> ExecutionReport:
        report = ExecutionReport()
        migrations = [op for op in plan.operations if isinstance(op, MigrateSourceMedia)]
        source_updates = [op for op in plan.operations if isinstance(op, WriteSourceMetadata)]
        shared_sources = {op.destination.resolve(): op for op in migrations}
        media_transfers = {
            (op.source.resolve(), op.destination): op for op in plan.operations
            if isinstance(op, TransferFile) and op.category == "media"
        }
        verified_before_updates = False
        cleanup_ready = False
        if migrations or source_updates:
            if plan.source_format != "pegasus" or plan.target_format != "es-de":
                raise FileOperationError("Source mutations are only allowed in a shared ES-DE plan")
            if plan.source_root.resolve().is_relative_to(plan.target_root.resolve()) or plan.target_root.resolve().is_relative_to(plan.source_root.resolve()):
                raise FileOperationError("Shared media source and target roots overlap")
            for update in source_updates:
                self._assert_source(plan.source_root, update.destination)
                self._check_source_metadata(update)
            for migration in migrations:
                self._assert_source(self._migration_root(plan, migration), migration.destination, allow_missing=True)
                if migration.expected_sha256 is None:
                    raise FileOperationError("A device-index migration must be executed on the device")
                if migration.destination.exists() and file_digest(migration.destination) != migration.expected_sha256:
                    raise FileOperationError(f"Source media changed: {migration.destination}")
                if not migration.destination.exists():
                    self._verify_migration_targets([migration])
                    if any(file_digest(update.destination) != hashlib.sha256(base64.b64decode(update.content_base64, validate=True)).hexdigest() for update in source_updates):
                        raise FileOperationError("Missing source media before metadata publication")
                for target in migration.targets:
                    self._assert_contained(plan.target_root, target)
                    transfer = media_transfers.get((migration.destination.resolve(), target))
                    if transfer is None or transfer.mode != MediaMode.COPY:
                        raise FileOperationError("Migration target has no copy operation")
                    if target.is_symlink() or (target.exists() and not target.is_file()):
                        raise FileOperationError(f"Invalid shared media target: {target}")
                    if target.exists() and file_digest(target) != migration.expected_sha256 and not transfer.overwrite:
                        raise FileOperationError(f"Existing shared media differs from source: {target}")
        for operation in plan.operations:
            if isinstance(operation, WriteText) and operation.expected_sha256 is not None:
                self._assert_contained(plan.target_root, operation.destination)
                self._check_baseline(operation)
        for operation in plan.operations:
            destination = operation.destination
            try:
                if isinstance(operation, (WriteSourceMetadata, MigrateSourceMedia)):
                    source_scope = self._migration_root(plan, operation) if isinstance(operation, MigrateSourceMedia) else plan.source_root
                    self._assert_source(source_scope, destination, allow_missing=isinstance(operation, MigrateSourceMedia))
                else:
                    self._assert_contained(plan.target_root, destination)
                if getattr(operation, "skipped", False):
                    report.skipped.append(destination)
                    continue
                if isinstance(operation, CreateDirectory):
                    destination.mkdir(parents=True, exist_ok=True)
                elif isinstance(operation, TransferFile):
                    migration = shared_sources.get(operation.source.resolve()) if operation.category == "media" else None
                    if migration and destination.is_file() and file_digest(destination) == migration.expected_sha256:
                        report.skipped.append(destination)
                        continue
                    self._transfer(operation)
                elif isinstance(operation, (WriteText, WriteManifest)):
                    if migrations and not verified_before_updates:
                        self._verify_migration_targets(migrations)
                        verified_before_updates = True
                    if isinstance(operation, WriteText):
                        self._check_baseline(operation)
                        if (
                            destination.is_file()
                            and destination.read_bytes() == operation.content.encode("utf-8")
                        ):
                            report.skipped.append(destination)
                            continue
                        if operation.backup and destination.is_file():
                            backup = destination.with_name(destination.name + ".frontendtrans.bak")
                            if not backup.exists():
                                shutil.copy2(destination, backup)
                    self._write_text(destination, operation.content, operation.overwrite)
                elif isinstance(operation, WriteSourceMetadata):
                    if not verified_before_updates:
                        self._verify_migration_targets(migrations)
                        verified_before_updates = True
                    self._check_source_metadata(operation)
                    data = base64.b64decode(operation.content_base64, validate=True)
                    if destination.read_bytes() == data:
                        report.skipped.append(destination)
                        continue
                    backup = self._source_backup(operation)
                    if not backup.exists():
                        shutil.copy2(destination, backup)
                    self._check_source_metadata(operation)
                    self._write_bytes(destination, data)
                elif isinstance(operation, MigrateSourceMedia):
                    if not cleanup_ready:
                        self._verify_migration_targets(migrations)
                        for update in source_updates:
                            desired = hashlib.sha256(base64.b64decode(update.content_base64, validate=True)).hexdigest()
                            if file_digest(update.destination) != desired:
                                raise FileOperationError("Source metadata is not fully published; cleanup stopped")
                        cleanup_ready = True
                    if not operation.cleanup:
                        report.skipped.append(destination)
                        continue
                    if not destination.exists():
                        report.skipped.append(destination)
                        continue
                    if file_digest(destination) != operation.expected_sha256:
                        raise FileOperationError(f"Source media changed before cleanup: {destination}")
                    self._verify_migration_targets([operation])
                    destination.unlink()
                report.completed.append(destination)
            except (OSError, FileOperationError) as exc:
                raise FileOperationError(f"Failed operation at {destination}: {exc}") from exc
        return report

    @staticmethod
    def _migration_root(plan: ConversionPlan, operation: MigrateSourceMedia) -> Path:
        media = plan.target_root.resolve() / "downloaded_media"
        if not operation.cleanup and operation.destination.resolve().is_relative_to(media):
            return media
        return plan.source_root

    @classmethod
    def _assert_source(cls, root: Path, path: Path, *, allow_missing: bool = False) -> None:
        cls._assert_contained(root, path)
        if path.is_symlink() or (not path.is_file() and (path.exists() or not allow_missing)):
            raise FileOperationError(f"Missing or linked shared-media source: {path}")
        for parent in path.parents:
            if parent == root.resolve():
                break
            if parent.is_symlink():
                raise FileOperationError(f"Linked shared-media source directory: {parent}")

    @staticmethod
    def _check_source_metadata(operation: WriteSourceMetadata) -> None:
        data = base64.b64decode(operation.content_base64, validate=True)
        current = file_digest(operation.destination)
        desired = hashlib.sha256(data).hexdigest()
        if current not in {operation.expected_sha256, desired}:
            raise FileOperationError(f"Source metadata changed after planning: {operation.destination}")
        backup = PlanExecutor._source_backup(operation)
        if backup.is_symlink() or (backup.exists() and not backup.is_file()):
            raise FileOperationError(f"Invalid metadata backup: {backup}")
        if backup.exists() and file_digest(backup) != operation.expected_sha256:
            raise FileOperationError(f"Metadata backup belongs to another baseline: {backup}")

    @staticmethod
    def _source_backup(operation: WriteSourceMetadata) -> Path:
        return operation.destination.with_name(
            operation.destination.name + ".frontendtrans." + operation.expected_sha256 + ".bak"
        )

    @staticmethod
    def _verify_migration_targets(migrations: list[MigrateSourceMedia]) -> None:
        for migration in migrations:
            for target in migration.targets:
                if not target.is_file() or target.is_symlink() or file_digest(target) != migration.expected_sha256:
                    raise FileOperationError(f"Shared media copy not verified: {target}")

    @staticmethod
    def _write_bytes(destination: Path, data: bytes) -> None:
        descriptor, name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _assert_contained(root: Path, destination: Path) -> None:
        try:
            destination.resolve(strict=False).relative_to(root.resolve(strict=False))
        except ValueError as exc:
            raise FileOperationError(f"Destination escaped target root: {destination}") from exc

    @staticmethod
    def _prepare(destination: Path, overwrite: bool) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            if not overwrite:
                raise FileOperationError(f"Target changed after planning: {destination}")
            if destination.is_dir() and not destination.is_symlink():
                raise FileOperationError(f"Cannot overwrite directory: {destination}")

    def _transfer(self, operation: TransferFile) -> None:
        if not operation.source.is_file():
            raise FileOperationError(f"Source file is missing: {operation.source}")
        self._prepare(operation.destination, operation.overwrite)
        if operation.mode in {RomMode.COPY, MediaMode.COPY}:
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{operation.destination.name}.",
                suffix=".tmp",
                dir=operation.destination.parent,
            )
            os.close(file_descriptor)
            temporary = Path(temporary_name)
            try:
                shutil.copy2(operation.source, temporary)
                if temporary.stat().st_size != operation.source.stat().st_size:
                    raise FileOperationError(f"Incomplete copy: {operation.source}")
                os.replace(temporary, operation.destination)
            finally:
                temporary.unlink(missing_ok=True)
        elif operation.mode == RomMode.MOVE:
            shutil.move(operation.source, operation.destination)
        # Legacy symbolic-link export is outside this project's test scope.
        elif operation.mode in {RomMode.SYMLINK, MediaMode.SYMLINK}:  # pragma: no cover
            if operation.destination.exists() or operation.destination.is_symlink():
                operation.destination.unlink()
            os.symlink(operation.source.resolve(), operation.destination)
        elif operation.mode in {RomMode.HARDLINK, MediaMode.HARDLINK}:
            if operation.destination.exists() or operation.destination.is_symlink():
                operation.destination.unlink()
            os.link(operation.source, operation.destination)
        else:
            raise FileOperationError(f"Unsupported transfer mode: {operation.mode}")

    @staticmethod
    def _check_baseline(operation: WriteText) -> None:
        if operation.expected_sha256 is None:
            return
        if operation.destination.is_symlink() or (
            operation.destination.exists() and not operation.destination.is_file()
        ):
            raise FileOperationError(f"Invalid configuration target: {operation.destination}")
        current = (
            hashlib.sha256(operation.destination.read_bytes()).hexdigest()
            if operation.destination.is_file()
            else ""
        )
        desired = hashlib.sha256(operation.content.encode("utf-8")).hexdigest()
        if current not in {operation.expected_sha256, desired}:
            raise FileOperationError(
                f"Configuration changed after planning: {operation.destination}"
            )

    def _write_text(self, destination: Path, content: str, overwrite: bool) -> None:
        self._prepare(destination, overwrite)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
