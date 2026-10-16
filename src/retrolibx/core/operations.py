"""Side-effect-free export intents and executable conversion plans."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .models import Diagnostic
from .options import ConflictPolicy, MediaMode, RomMode


class FileRequest(BaseModel):
    source: Path
    destination: PurePosixPath
    category: Literal["rom", "media"]


class TextRequest(BaseModel):
    destination: PurePosixPath
    content: str
    expected_sha256: str | None = None
    backup: bool = False


class MediaBinding(BaseModel):
    system_id: str
    game_index: int
    role: str
    destination: PurePosixPath


class SourceMetadataUpdate(BaseModel):
    source: Path
    content_base64: str
    expected_sha256: str


class MediaRelocation(BaseModel):
    source: Path
    destinations: list[PurePosixPath]
    expected_sha256: str | None = None
    cleanup: bool = True


class ExportIntent(BaseModel):
    media_bindings: list[MediaBinding] = Field(default_factory=list)
    directories: list[PurePosixPath] = Field(default_factory=list)
    files: list[FileRequest] = Field(default_factory=list)
    texts: list[TextRequest] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    source_metadata_updates: list[SourceMetadataUpdate] = Field(default_factory=list)
    media_relocations: list[MediaRelocation] = Field(default_factory=list)


class CreateDirectory(BaseModel):
    kind: Literal["mkdir"] = "mkdir"
    destination: Path


class TransferFile(BaseModel):
    kind: Literal["transfer"] = "transfer"
    source: Path
    destination: Path
    category: Literal["rom", "media"]
    mode: RomMode | MediaMode
    overwrite: bool = False
    skipped: bool = False
    skip_reason: str | None = None


class WriteText(BaseModel):
    kind: Literal["write_text"] = "write_text"
    destination: Path
    content: str
    overwrite: bool = False
    skipped: bool = False
    skip_reason: str | None = None
    expected_sha256: str | None = None
    backup: bool = False


class WriteManifest(BaseModel):
    kind: Literal["write_manifest"] = "write_manifest"
    destination: Path
    content: str
    overwrite: bool = True


class WriteSourceMetadata(BaseModel):
    kind: Literal["write_source_metadata"] = "write_source_metadata"
    destination: Path
    content_base64: str
    expected_sha256: str


class MigrateSourceMedia(BaseModel):
    kind: Literal["migrate_source_media"] = "migrate_source_media"
    destination: Path
    targets: list[Path]
    expected_sha256: str | None = None
    cleanup: bool = True


Operation = Annotated[
    CreateDirectory | TransferFile | WriteText | WriteManifest | WriteSourceMetadata | MigrateSourceMedia,
    Field(discriminator="kind"),
]


class ConversionPlan(BaseModel):
    source_root: Path
    target_root: Path
    source_format: str
    target_format: str
    conflict_policy: ConflictPolicy
    operations: list[Operation] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)

    @property
    def actionable_count(self) -> int:
        return sum(not getattr(op, "skipped", False) for op in self.operations)


class ExecutionReport(BaseModel):
    completed: list[Path] = Field(default_factory=list)
    skipped: list[Path] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
