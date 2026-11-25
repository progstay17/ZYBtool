"""Tolerant metadata, log and CSV parsing. No filesystem mutation occurs here."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from zybtool.models import CsvTimeline, SessionFacts, UnitKind

_STOP_DURATION = re.compile(r"\bstop\b.*?\bdur=([0-9]+(?:\.[0-9]+)?)s", re.IGNORECASE)
_RESTART = re.compile(r"\bRESTART\b", re.IGNORECASE)


def _load_json(path: Path, warnings: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        warnings.append(f"{path.name}: JSON tidak dapat dibaca ({type(exc).__name__})")
        return {}
    if not isinstance(value, dict):
        warnings.append(f"{path.name}: akar JSON bukan object")
        return {}
    return value


def parse_csv_timeline(path: Path, relative_path: str) -> CsvTimeline:
    first: int | None = None
    last: int | None = None
    rows = 0
    monotonic = True
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "mono_us" not in reader.fieldnames:
                return CsvTimeline(relative_path, error="Kolom mono_us tidak ditemukan")
            for row in reader:
                raw = row.get("mono_us")
                try:
                    current = int(raw) if raw is not None else None
                except ValueError:
                    continue
                if current is None:
                    continue
                if first is None:
                    first = current
                if last is not None and current < last:
                    monotonic = False
                last = current
                rows += 1
    except (OSError, UnicodeError, csv.Error) as exc:
        return CsvTimeline(relative_path, error=f"CSV tidak dapat dibaca ({type(exc).__name__})")
    return CsvTimeline(relative_path, first, last, rows, monotonic)


def parse_unit_metadata(
    root: Path,
    relative_path: str,
    kind: UnitKind,
    files: tuple[Path, ...],
) -> SessionFacts:
    warnings: list[str] = []
    by_name: dict[str, list[Path]] = {}
    for path in files:
        by_name.setdefault(path.name.lower(), []).append(path)

    def first(name: str) -> Path | None:
        matches = sorted(by_name.get(name.lower(), []), key=lambda p: p.as_posix().lower())
        return matches[0] if matches else None

    session_path = first("session.json")
    sync_path = first("session_sync.json")
    t0_path = first("t0.json")
    session = _load_json(session_path, warnings) if session_path else {}
    sync = _load_json(sync_path, warnings) if sync_path else {}
    t0 = _load_json(t0_path, warnings) if t0_path else {}

    logs = [p for p in files if p.name.lower() == "app.log"]
    durations: list[float] = []
    stop_seen = False
    restart_count = 0
    for log_path in sorted(logs, key=lambda p: p.as_posix().lower()):
        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if re.search(r"\bstop\b", line, re.IGNORECASE):
                        stop_seen = True
                    durations.extend(float(m.group(1)) for m in _STOP_DURATION.finditer(line))
                    restart_count += len(_RESTART.findall(line))
        except OSError as exc:
            warnings.append(f"{log_path.name}: log tidak dapat dibaca ({type(exc).__name__})")

    csv_timelines = tuple(
        parse_csv_timeline(path, path.relative_to(root).as_posix())
        for path in sorted(files, key=lambda p: p.as_posix().lower())
        if "frametimes" in path.name.lower() and path.suffix.lower() == ".csv"
    )
    meta_files = [
        path
        for path in files
        if path.name.lower() == "meta.json" and path.parent.name.lower() not in {"", "."}
    ]
    mkv_files = sorted(
        (path for path in files if path.suffix.lower() == ".mkv"),
        key=lambda p: p.relative_to(root).as_posix().lower(),
    )
    camera_dirs = sorted(
        {path.parent.relative_to(root).as_posix() for path in meta_files}
        | {path.parent.relative_to(root).as_posix() for path in mkv_files}
    )

    missing: list[str] = []
    for name, candidate_path in (
        ("session.json", session_path),
        ("session_sync.json", sync_path),
        ("t0.json", t0_path),
    ):
        if candidate_path is None:
            missing.append(name)
    if not meta_files:
        missing.append("camera meta.json")
    if not mkv_files:
        missing.append("video MKV")
    if not csv_timelines:
        missing.append("IMU frametimes CSV")

    stereo_raw = sync.get("stereo")
    stereo_sync: dict[str, Any] = stereo_raw if isinstance(stereo_raw, dict) else {}
    fails_raw = sync.get("fails", [])
    if not isinstance(fails_raw, list):
        fails_raw = [str(fails_raw)]
    sync_fails = tuple(str(item) for item in fails_raw)

    created = session.get("created")
    t0_wall = t0.get("t_wall_s")
    if t0_wall is None:
        capture = session.get("capture_t0")
        if isinstance(capture, dict):
            t0_wall = capture.get("t_wall_s")

    return SessionFacts(
        relative_path=relative_path,
        kind=kind,
        device_id=_optional_str(session.get("device_id")),
        object_id=_optional_str(session.get("object_id")),
        live_root=_optional_str(session.get("live_root")),
        capture_date=_optional_str(session.get("capture_date")),
        created_epoch=_optional_float(created),
        capture_t0_wall_s=_optional_float(t0_wall),
        segment_start_wall=_optional_float(session.get("segment_start_wall")),
        segment_stop_wall=_optional_float(session.get("segment_stop_wall")),
        claimed_video_duration_s=_optional_float(session.get("video_duration_s")),
        sync_wall_s=_optional_float(sync.get("wall_s") or stereo_sync.get("duration")),
        sync_ok=sync.get("ok") if isinstance(sync.get("ok"), bool) else None,
        sync_fails=sync_fails,
        log_stop_durations_s=tuple(durations),
        has_stop_log=stop_seen,
        restart_count=restart_count,
        camera_dirs=tuple(camera_dirs),
        mkv_paths=tuple(path.relative_to(root).as_posix() for path in mkv_files),
        csv_timelines=csv_timelines,
        missing_files=tuple(sorted(set(missing))),
        warnings=tuple(warnings),
    )


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        result = float(value)
        return result if result == result and abs(result) != float("inf") else None
    except (TypeError, ValueError):
        return None
