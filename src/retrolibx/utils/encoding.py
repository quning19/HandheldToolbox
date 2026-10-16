"""Automatic text decoding for Pegasus metadata, without a UI encoding setting."""

from retrolibx.errors import ValidationError


def detect_metadata_encoding(raw: bytes) -> str:
    candidates = ["utf-16"] if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else ["utf-8-sig", "gb18030"]
    for encoding in candidates:
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeError:
            continue
    raise ValidationError("无法自动识别 metadata 编码")

