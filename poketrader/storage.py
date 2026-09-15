"""Durable local files. Never follow user-supplied paths from the network."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path: Path, value):
    atomic_write(path, (json.dumps(value, indent=2)+"\n").encode())


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
