"""Small deterministic helpers and safe filesystem primitives."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def is_symlink(path: Path) -> bool:
    try:
        return path.is_symlink()
    except OSError:
        return True


def safe_walk(root: Path) -> Iterable[tuple[Path, list[str], list[str]]]:
    """Walk without following directory or file symlinks; results are sorted."""
    for current, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
        base = Path(current)
        dir_names[:] = sorted(name for name in dir_names if not is_symlink(base / name))
        safe_files = sorted(name for name in file_names if not is_symlink(base / name))
        yield base, dir_names, safe_files


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    try:
        with temp.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except FileExistsError:
        raise FileExistsError(f"File sementara sudah ada: {temp}") from None
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def stable_run_id(source_root: Path, relative_paths: Iterable[str]) -> str:
    payload = {"root_name": source_root.name, "paths": sorted(relative_paths)}
    return sha256_bytes(canonical_json_bytes(payload))[:16]
