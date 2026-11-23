"""Encrypted on-disk storage for face templates (embeddings only, never photos) using Windows DPAPI."""
from __future__ import annotations

import ctypes
import json
from ctypes import wintypes
from pathlib import Path

from . import config


class _Blob(ctypes.Structure):
    """A Windows DATA_BLOB structure used to pass bytes to the DPAPI functions."""

    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _to_blob(data: bytes):
    """Wraps bytes in a DATA_BLOB and returns it with the buffer that must stay alive."""
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _from_blob(blob: _Blob) -> bytes:
    """Copies bytes out of a DPAPI-returned DATA_BLOB and frees the Windows-allocated memory."""
    out = ctypes.string_at(blob.pbData, blob.cbData)
    ctypes.windll.kernel32.LocalFree(blob.pbData)
    return out


def dpapi_encrypt(data: bytes) -> bytes:
    """Encrypts bytes so only the current Windows user can decrypt them."""
    blob_in, _keep = _to_blob(data)
    blob_out = _Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(blob_in), "KidGuard", None, None, None, 0, ctypes.byref(blob_out)):
        raise OSError("CryptProtectData failed")
    return _from_blob(blob_out)


def dpapi_decrypt(data: bytes) -> bytes:
    """Decrypts bytes previously produced by dpapi_encrypt for the same Windows user."""
    blob_in, _keep = _to_blob(data)
    blob_out = _Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise OSError("CryptUnprotectData failed")
    return _from_blob(blob_out)


def save_templates(templates: dict, path: Path = config.TEMPLATES_PATH) -> None:
    """Serialises the templates to JSON, encrypts them and writes them to disk."""
    payload = {
        name: {"role": e["role"], "embeddings": [[float(x) for x in v] for v in e["embeddings"]]}
        for name, e in templates.items()
    }
    Path(path).write_bytes(dpapi_encrypt(json.dumps(payload).encode("utf-8")))


def load_templates(path: Path = config.TEMPLATES_PATH) -> dict:
    """Reads and decrypts the templates file, returning an empty dict if it does not exist."""
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(dpapi_decrypt(p.read_bytes()).decode("utf-8"))


def delete_all(path: Path = config.TEMPLATES_PATH) -> bool:
    """Deletes the stored templates file (PRD F12) and returns True if a file was removed."""
    p = Path(path)
    if p.exists():
        p.unlink()
        return True
    return False
