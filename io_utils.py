#!/usr/bin/env python3
"""
Local LLM-ready Compressor
File: io_utils.py
Copyright (C) 2026 Cristian Evangelisti
License: GPL-3.0-or-later
SPDX-License-Identifier: GPL-3.0-or-later
Source: https://github.com/kamaludu/chunk-compress

Description:
Safe, atomic I/O utilities optimized for large files:
- Directory creation with recursive parents support.
- Streamed atomic file writing without heap duplication.
- Buffered SHA256 file and text hashing.
- Atomic JSON serialization.
"""

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Optional, Union

PathLike = Union[str, Path]


def ensure_dir(path: PathLike) -> None:
    """
    Ensure the parent or target directory exists, creating parents recursively.
    """
    Path(path).mkdir(parents=True, exist_ok=True)


def read_bytes(path: PathLike) -> bytes:
    """
    Read and return raw file bytes.
    """
    p = Path(path)
    with p.open("rb") as f:
        return f.read()


def read_text(path: PathLike, encoding: str = "utf-8", errors: str = "strict") -> str:
    """
    Read file as text with specified encoding and error handling.
    """
    p = Path(path)
    with p.open("r", encoding=encoding, errors=errors) as f:
        return f.read()


def read_utf8(path: PathLike) -> str:
    """
    Backwards-compatible alias for read_text with UTF-8 encoding.
    """
    return read_text(path, encoding="utf-8", errors="strict")


def safe_remove(path: PathLike) -> None:
    """
    Silently remove a file if it exists, ignoring OS errors.
    """
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
    except Exception:
        pass


def write_atomic(path: PathLike, data: Union[str, bytes], encoding: str = "utf-8") -> None:
    """
    Write data atomically to destination path using a temporary file in the same directory.
    Avoids duplicate memory allocations on large strings by streaming text directly via os.fdopen.
    Guarantees cross-platform replacement and flushes to disk via fsync where supported.
    """
    p = Path(path)
    ensure_dir(p.parent)

    fd = None
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix=p.name + ".", dir=str(p.parent))
        if isinstance(data, str):
            # Stream directly in text mode to avoid allocating duplicate bytes buffer in heap
            with os.fdopen(fd, "w", encoding=encoding, errors="strict") as f:
                f.write(data)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
        else:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass

        # Atomic replacement (tempfile is closed and replaced)
        os.replace(tmp_path, str(p))
        tmp_path = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def sha256_file(path: PathLike, buffer_size: int = 65536) -> str:
    """
    Compute SHA256 checksum of a file using 64 KB buffers to optimize I/O on large files.
    """
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(buffer_size), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(s: str, encoding: str = "utf-8") -> str:
    """
    Compute SHA256 checksum of a string encoded in UTF-8.
    """
    return hashlib.sha256(s.encode(encoding)).hexdigest()


def write_json_atomic(path: PathLike, obj: Any, **json_kwargs: Any) -> None:
    """
    Serialize obj to JSON and write atomically to disk.
    Defaults to indent=2 and ensure_ascii=False for UTF-8 readability.
    """
    kwargs = {"ensure_ascii": False, "indent": 2}
    kwargs.update(json_kwargs)
    data = json.dumps(obj, **kwargs)
    write_atomic(path, data, encoding="utf-8")
