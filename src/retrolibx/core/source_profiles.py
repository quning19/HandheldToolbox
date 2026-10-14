"""Explicit source conventions, separate from frontend file formats."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from retrolibx.errors import ValidationError

from .models import Game, Media


class SourceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    name: str = "generic"
    media_directory: str | None = None
    media_fallbacks: dict[str, str | list[str]] = Field(default_factory=dict)
    developer_as_version_note: bool = False
    version_note_label: str = "版本说明"
    confirmation_systems: list[str] = Field(default_factory=list)

    @field_validator("media_directory")
    @classmethod
    def relative_media_directory(cls, value: str | None) -> str | None:
        if value is None:
            return value
        path = Path(value.replace("\\", "/"))
        if (
            not value or path.is_absolute() or path.drive or ".." in path.parts
            or ":" in value or any(c in value for c in "\r\n\t\x00")
        ):
            raise ValueError("media_directory must stay inside the source platform")
        return path.as_posix()

    @field_validator("media_fallbacks")
    @classmethod
    def media_roles_and_stems(cls, value: dict[str, str | list[str]]) -> dict[str, str | list[str]]:
        for role, stem in value.items():
            if role not in Media.model_fields or role == "extra":
                raise ValueError("Unknown fallback media role: " + role)
            stems = stem if isinstance(stem, list) else [stem]
            if not stems:
                raise ValueError("Fallback media names cannot be empty")
            for name in stems:
                if (
                    not name or name in {".", ".."}
                    or any(c in name for c in '/\\:\r\n\t\x00')
                ):
                    raise ValueError("Fallback media name must be a file stem")
        return value

    @classmethod
    def load(cls, path: Path | None = None, *, default: str = "generic") -> "SourceProfile":
        if path is None:
            if default not in {"generic", "pegasus-g"}:
                raise ValidationError("Unknown bundled source profile: " + default)
            path = Path(__file__).parents[1] / "profiles" / (default + ".json")
        try:
            return cls.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValidationError(f"Cannot load source profile {path}: {exc}") from exc

    def normalize_game(self, game: Game) -> None:
        """Retain raw source fields while explicitly normalizing a version-note convention."""
        developer = game.developer
        if not self.developer_as_version_note or not developer:
            return
        if developer != game.name and not developer.startswith(game.name + " "):
            return
        if developer != game.name:
            note = self.version_note_label + ": " + developer
            if note not in (game.description or "").splitlines():
                game.description = (game.description or "") + "\n\n" + note
            game.source_metadata["version_note"] = developer
        game.developer = None
