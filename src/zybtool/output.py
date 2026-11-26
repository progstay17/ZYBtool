"""Deterministic local output planning and naming."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zybtool.models import ResultStatus, VerificationReport
from zybtool.naming import build_folder_name


@dataclass(frozen=True, slots=True)
class OutputItem:
    recording_id: str
    folder_name: str
    unit_paths: tuple[str, ...]
    status: str
    named: bool
    reason: str
    qr_metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class OutputPlan:
    source_root: str
    destination: str
    items: tuple[OutputItem, ...]
    blocked: tuple[str, ...]


def _load_native_session(source: Path, recording: Any) -> dict[str, Any]:
    """Read only the canonical session.json for the first unit in a recording."""
    for relative in recording.unit_paths:
        candidate = source / relative
        if candidate.is_symlink():
            raise ValueError("Symlink recording tidak diizinkan untuk naming metadata.")
        unit_dir = candidate.resolve(strict=True)
        if unit_dir != source and source not in unit_dir.parents:
            raise ValueError("Path session keluar dari folder sumber.")
        session_file = unit_dir / "session.json"
        if not session_file.is_file() or session_file.is_symlink():
            continue
        try:
            value = json.loads(session_file.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"session.json tidak dapat dibaca ({type(exc).__name__}).") from None
        if not isinstance(value, dict):
            raise ValueError("Akar session.json harus berupa object.")
        return value
    return {}


def _operational_name(
    recording: Any,
    report: VerificationReport,
    naming_config: dict[str, Any] | None = None,
) -> str:
    payload = recording.qr.payload if recording.qr else None
    if not isinstance(payload, dict):
        raise ValueError("Payload QR tidak tersedia.")
    facts = {item.relative_path: item for item in report.units}
    dates = {
        re.sub(r"[^0-9]", "", facts[path].capture_date or "")
        for path in recording.unit_paths
        if path in facts and facts[path].capture_date
    }
    dates = {value for value in dates if len(value) == 8}
    if len(dates) > 1:
        raise ValueError("Tanggal capture tidak tersedia atau ambigu.")
    session = _load_native_session(Path(report.source_root).resolve(strict=True), recording)
    capture_date = dates.pop() if dates else None
    return build_folder_name(payload, session, capture_date, naming_config)


def create_output_plan(
    report: VerificationReport,
    destination: Path | str,
    naming_config: dict[str, Any] | None = None,
) -> OutputPlan:
    source = Path(report.source_root).resolve(strict=True)
    target = Path(destination).expanduser().resolve()
    if target == source or target in source.parents or source in target.parents:
        raise ValueError("Folder output harus terpisah dari folder sumber.")
    if target.exists() and not target.is_dir():
        raise FileExistsError("Path Organized Folders sudah ada tetapi bukan folder.")

    items: list[OutputItem] = []
    blocked: list[str] = []
    for recording in report.recordings:
        if not recording.unit_paths:
            blocked.append(f"{recording.recording_id}: tidak memiliki folder sumber.")
            continue
        if recording.status is ResultStatus.CORRUPTED:
            items.append(
                OutputItem(
                    recording.recording_id,
                    "_REJECTED",
                    recording.unit_paths,
                    recording.status.value,
                    False,
                    "Recording corrupt dipisahkan ke _REJECTED seperti ZYWTool.",
                )
            )
            continue
        if recording.status in {
            ResultStatus.METADATA_ONLY,
            ResultStatus.QR_MISSING,
            ResultStatus.QR_DECRYPT_FAILED,
        }:
            items.append(
                OutputItem(
                    recording.recording_id,
                    f"_UNNAMED/{recording.recording_id[:16]}",
                    recording.unit_paths,
                    recording.status.value,
                    False,
                    "QR belum dapat didekripsi; folder dipindahkan tanpa nama operasional.",
                )
            )
            continue
        if (
            recording.status is not ResultStatus.VERIFIED
            or recording.trust_level < 3
            or recording.qr is None
            or recording.qr.status is not ResultStatus.QR_DECRYPTED
        ):
            blocked.append(
                f"{recording.recording_id}: {recording.status.value}, trust level {recording.trust_level}; "
                "butuh QR MQ1 yang berhasil didekripsi dan korelasi metadata/video."
            )
            continue
        try:
            name = _operational_name(recording, report, naming_config)
        except ValueError as exc:
            blocked.append(f"{recording.recording_id}: {exc}")
            continue
        items.append(
            OutputItem(
                recording.recording_id,
                name,
                recording.unit_paths,
                recording.status.value,
                True,
                "QR berhasil didekripsi; envelope dan pemeriksaan recording valid. Metadata QR dipakai untuk melengkapi session.json.",
                {
                    "schema": "zyb-recording/v1",
                    "payload": dict(recording.qr.payload or {}),
                    "verification": {
                        "status": recording.qr.status.value,
                        "recording_status": recording.status.value,
                        "trust_level": recording.trust_level,
                        "token_id": recording.qr.token_id,
                        "token_version": recording.qr.token_version,
                        "source_video": recording.qr.source_video,
                        "first_seen_s": recording.qr.time_s,
                    },
                },
            )
        )

    # Like ZYWTool, recordings with the same operational key share one group folder.
    # Keep each recording separate so its own QR metadata enriches its own session.json.
    claimed_paths: set[str] = set()
    for item in items:
        for relative in item.unit_paths:
            key = (Path(item.folder_name) / relative).as_posix().casefold()
            if key in claimed_paths:
                raise ValueError(f"Bentrokan path recording di dalam grup: {key}")
            claimed_paths.add(key)
    return OutputPlan(str(source), str(target), tuple(items), tuple(blocked))
