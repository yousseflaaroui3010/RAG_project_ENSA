"""Documents added, downloaded and removed from the browser (S6).

2026-09-13 human ruling (DECISIONS, CR-03): documents are uploaded in the
browser. UX spec 13 ruled drag-and-drop out "because workspaces point at
folders on disk" -- and they still do. An upload here is a file WRITTEN
INTO THE WORKSPACE'S OWN FOLDER, and the ordinary Sync then indexes it
exactly as it would a file the operator copied there by hand. Nothing
about change detection, conversion or the registry changes; there is one
way a document enters the index, and it is still the folder.

THE FILE NAME IS HOSTILE INPUT. It arrives from a browser, and a name like
`..\\..\\app.py` or `CON.pdf` is a write outside the folder or a Windows
device, not a document. `checked_name` accepts one plain file name with a
supported extension and nothing else; every function here goes through it,
and every resolved path is checked to sit directly inside the folder.

WRITES ARE ALL OR NOTHING. The bytes go to a hidden temporary file in the
same folder and are moved over the final name in one `os.replace`, so a
Sync or the folder watcher never sees half a PDF, and an upload that fails
or is too large leaves nothing behind. The temporary name ends in `.part`,
which no supported extension matches, so even a Sync that lists the
folder mid-upload skips it.
"""

from __future__ import annotations

import contextlib
import os
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from config import get_settings

# Longest file name most file systems accept, in characters.
MAX_NAME_CHARS = 255

# Windows device names are reserved with ANY extension ("con.pdf" opens the
# console). Checked on every platform: a workspace folder can be copied to
# a Windows machine, and the demo runs on one.
_RESERVED_STEMS = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
# Path separators, drive colons, and every control character including NUL.
_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')

_TEMP_SUFFIX = ".part"


class DocumentError(Exception):
    """A request about one document that cannot be honoured.

    `key` is the ui.i18n catalog key for the reader's sentence and
    `params` fill it; `status` is the HTTP status the route answers with.
    The English `str()` is for logs and tests."""

    def __init__(self, key: str, status: int, message: str, **params: object) -> None:
        super().__init__(message)
        self.key = key
        self.status = status
        self.params = params


@dataclass(frozen=True)
class SavedDocument:
    file_name: str
    size_bytes: int
    replaced: bool


def checked_name(raw: str) -> str:
    """One plain, supported file name, or `DocumentError`."""
    name = (raw or "").strip()
    if not name or len(name) > MAX_NAME_CHARS or name in {".", ".."}:
        raise DocumentError("docs.error.name", 400, f"not a usable file name: {raw!r}")
    if _FORBIDDEN.search(name) or name.startswith(".") or name.endswith((".", " ")):
        raise DocumentError("docs.error.name", 400, f"not a usable file name: {raw!r}")
    stem, _, extension = name.rpartition(".")
    if stem.split(".")[0].lower() in _RESERVED_STEMS:
        raise DocumentError("docs.error.name", 400, f"reserved device name: {raw!r}")
    allowed = get_settings().supported_document_extensions
    if not stem or extension.lower() not in allowed:
        raise DocumentError(
            "docs.error.type",
            415,
            f"{name!r} is not one of the supported types {allowed}",
            types=", ".join(allowed),
        )
    return name


def _inside(folder: Path, name: str) -> Path:
    """The path `name` names directly inside `folder`, proven, not assumed."""
    root = folder.resolve()
    target = (root / name).resolve()
    if target.parent != root:
        raise DocumentError("docs.error.name", 400, f"{name!r} escapes the workspace folder")
    return target


def existing_document(folder: str | Path, raw_name: str) -> Path:
    """The file to download or remove: supported, inside, and present."""
    name = checked_name(raw_name)
    path = _inside(Path(folder), name)
    if not path.is_file():
        raise DocumentError("docs.error.missing", 404, f"no document named {name!r}", name=name)
    return path


async def save_document(
    folder: str | Path, raw_name: str, chunks: AsyncIterator[bytes], *, declared_size: int | None
) -> SavedDocument:
    """Write one uploaded file into the workspace folder, atomically.

    `declared_size` is the request's Content-Length when it sent one; a
    body over the limit is refused before a byte is written. The running
    count below is what actually enforces it, because a declared length
    can be absent or wrong."""
    limit = get_settings().upload_max_bytes
    name = checked_name(raw_name)
    root = Path(folder)
    if not root.is_dir():
        raise DocumentError("docs.error.folder", 409, f"the workspace folder {folder!r} is missing")
    final = _inside(root, name)
    if declared_size is not None and declared_size > limit:
        raise DocumentError("docs.error.size", 413, f"{name!r} is over {limit} bytes", name=name)

    temp = root / f".{uuid.uuid4().hex}{_TEMP_SUFFIX}"
    written = 0
    try:
        with open(temp, "xb") as out:
            async for chunk in chunks:
                written += len(chunk)
                if written > limit:
                    raise DocumentError(
                        "docs.error.size", 413, f"{name!r} is over {limit} bytes", name=name
                    )
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        if written == 0:
            raise DocumentError("docs.error.empty", 400, f"{name!r} is empty", name=name)
        replaced = final.exists()
        os.replace(temp, final)
    except BaseException:
        with contextlib.suppress(OSError):
            temp.unlink()
        raise
    return SavedDocument(file_name=name, size_bytes=written, replaced=replaced)


def remove_document(folder: str | Path, raw_name: str) -> str:
    """Delete one document file from the workspace folder; its name."""
    path = existing_document(folder, raw_name)
    path.unlink()
    return path.name
