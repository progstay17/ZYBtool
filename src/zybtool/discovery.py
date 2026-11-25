"""Deterministic recording discovery, including hidden live folders."""

from __future__ import annotations

from pathlib import Path

from zybtool.meta import parse_unit_metadata
from zybtool.models import Unit, UnitKind
from zybtool.util import is_symlink, safe_walk

_CAMERA_NAMES = {"stereo", "wrists", "gloves", "bands"}
_LIVE_PREFIX = ".live_"
_PRIMARY_PREFIX = "recording_primary_"


def _candidate_directories(root: Path) -> set[Path]:
    candidates: set[Path] = set()
    mkv_files: list[Path] = []
    for directory, _, file_names in safe_walk(root):
        if "session.json" in {name.lower() for name in file_names}:
            candidates.add(directory)
        if directory.name.lower().startswith((_LIVE_PREFIX, _PRIMARY_PREFIX)):
            candidates.add(directory)
        mkv_files.extend(directory / name for name in file_names if name.lower().endswith(".mkv"))

    for video in mkv_files:
        camera_dir = video.parent
        if (camera_dir / "meta.json").is_file() or camera_dir.name.lower() in _CAMERA_NAMES:
            candidates.add(camera_dir.parent)
        else:
            candidates.add(camera_dir)
    return {path for path in candidates if path == root or root in path.parents}


def _files_for_candidate(candidate: Path, nested_candidates: set[Path]) -> tuple[Path, ...]:
    collected: list[Path] = []
    for directory, dir_names, file_names in safe_walk(candidate):
        if directory != candidate:
            dir_names[:] = [name for name in dir_names if directory / name not in nested_candidates]
        for name in file_names:
            path = directory / name
            if not is_symlink(path):
                collected.append(path)
    return tuple(sorted(collected, key=lambda p: p.relative_to(candidate).as_posix().lower()))


def _classify(path: Path, files: tuple[Path, ...]) -> UnitKind:
    names = {item.name.lower() for item in files}
    if path.name.lower().startswith(_LIVE_PREFIX):
        return UnitKind.LIVE
    core = {"session.json", "session_sync.json", "t0.json"}
    has_meta = any(item.name.lower() == "meta.json" for item in files)
    if core.issubset(names) and has_meta:
        return UnitKind.FINAL
    return UnitKind.PARTIAL


def discover_units(root: Path | str) -> tuple[Unit, ...]:
    """Find each independent recording unit without following symlinks."""
    source = Path(root).expanduser()
    if not source.exists() or not source.is_dir():
        raise NotADirectoryError(f"Folder sumber tidak ditemukan: {source}")
    if is_symlink(source):
        raise ValueError("Folder sumber tidak boleh berupa symlink")
    source = source.resolve(strict=True)

    candidates = _candidate_directories(source)
    ordered = sorted(candidates, key=lambda p: (len(p.parts), p.as_posix().lower()))
    selected: list[Path] = []
    for candidate in ordered:
        if any(parent in candidate.parents for parent in selected):
            if (candidate / "session.json").is_file():
                selected = [item for item in selected if item not in candidate.parents]
            else:
                continue
        selected.append(candidate)

    selected_set = set(selected)
    units: list[Unit] = []
    for candidate in sorted(selected, key=lambda p: p.relative_to(source).as_posix().lower()):
        nested = {path for path in selected_set if path != candidate and candidate in path.parents}
        files = _files_for_candidate(candidate, nested)
        kind = _classify(candidate, files)
        relative = "." if candidate == source else candidate.relative_to(source).as_posix()
        facts = parse_unit_metadata(candidate, relative, kind, files)
        units.append(Unit(candidate, facts))
    return tuple(units)
