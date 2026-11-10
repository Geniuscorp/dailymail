"""Validation rules for incoming attachments.

An attachment is accepted only when its extension is on the allow-list and its
leading bytes match the format that extension claims. The sender's declared
MIME type is never trusted; the stored MIME type comes from the allow-list.
"""
import re
from dataclasses import dataclass
from typing import Optional

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"PK\x03\x04"


@dataclass(frozen=True)
class FormatRule:
    mime_type: str
    magic: tuple[bytes, ...]  # empty tuple: no signature check (plain text)


ALLOWED_FORMATS: dict[str, FormatRule] = {
    "pdf": FormatRule("application/pdf", (b"%PDF-",)),
    "png": FormatRule("image/png", (b"\x89PNG\r\n\x1a\n",)),
    "jpg": FormatRule("image/jpeg", (b"\xff\xd8\xff",)),
    "jpeg": FormatRule("image/jpeg", (b"\xff\xd8\xff",)),
    "gif": FormatRule("image/gif", (b"GIF87a", b"GIF89a")),
    "txt": FormatRule("text/plain; charset=utf-8", ()),
    "doc": FormatRule("application/msword", (OLE_MAGIC,)),
    "xls": FormatRule("application/vnd.ms-excel", (OLE_MAGIC,)),
    "docx": FormatRule(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", (ZIP_MAGIC,)
    ),
    "xlsx": FormatRule(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", (ZIP_MAGIC,)
    ),
    "zip": FormatRule("application/zip", (ZIP_MAGIC,)),
}

MAX_FILENAME_LENGTH = 255
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class AttachmentRejectedError(Exception):
    """The attachment is not allowed; the message is still stored without it."""


@dataclass(frozen=True)
class AcceptedAttachment:
    original_filename: str
    extension: str
    mime_type: str
    data: bytes


def sanitize_filename(raw: Optional[str]) -> str:
    """Keep only the last path segment, without control characters, bounded in length."""
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = _CONTROL_CHARS.sub("", name).strip()
    if not name or name in {".", ".."}:
        return "anexo"
    return name[:MAX_FILENAME_LENGTH]


def extension_of(filename: str) -> str:
    _, dot, ext = filename.rpartition(".")
    return ext.lower() if dot else ""


def validate_attachment(raw_filename: Optional[str], data: bytes, max_bytes: int) -> AcceptedAttachment:
    if not data:
        raise AttachmentRejectedError("empty attachment")
    if len(data) > max_bytes:
        raise AttachmentRejectedError("attachment exceeds size limit")

    filename = sanitize_filename(raw_filename)
    extension = extension_of(filename)
    rule = ALLOWED_FORMATS.get(extension)
    if rule is None:
        raise AttachmentRejectedError("extension not allowed")

    if rule.magic:
        if not any(data.startswith(signature) for signature in rule.magic):
            raise AttachmentRejectedError("content does not match extension")
    elif b"\x00" in data:
        raise AttachmentRejectedError("text attachment contains binary data")

    return AcceptedAttachment(
        original_filename=filename,
        extension=extension,
        mime_type=rule.mime_type,
        data=data,
    )
