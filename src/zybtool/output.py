"""Deterministic local output planning and naming."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zybtool.models import ResultStatus, VerificationReport


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


def _safe_component(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field AITQR '{field}' kosong.")
    # Same normalization as ZYWTool's _alnum(): strip spaces and punctuation.
    result = re.sub(r"[^A-Za-z0-9]", "", value)
    if not result:
        raise ValueError(f"Field AITQR '{field}' tidak memiliki karakter alfanumerik.")
    if result.upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        raise ValueError(f"Field AITQR '{field}' memakai nama perangkat Windows yang dilarang.")
    return result


def _operational_name(recording: Any, report: VerificationReport) -> str:
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
    if len(dates) != 1:
        raise ValueError("Tanggal capture tidak tersedia atau ambigu.")
    date = dates.pop()
    branch = _safe_component(payload.get("b"), "b")
    recorder = _safe_component(payload.get("r"), "r")
    recorder_number = _safe_component(payload.get("dn"), "dn")
    activity = _safe_component(payload.get("a"), "a")
    shift = payload.get("sh")
    if not isinstance(shift, int) or isinstance(shift, bool) or shift not in (1, 2, 3):
        raise ValueError("Field AITQR 'sh' harus bernilai 1, 2, atau 3.")
    if not re.fullmatch(r"MM[0-9]{2,4}", branch):
        raise ValueError("Field AITQR 'b' harus berformat MM diikuti 2–4 digit.")
    if not re.fullmatch(r"ZY[0-9]{3,4}", recorder_number):
        raise ValueError("Field AITQR 'dn' harus berformat ZY diikuti 3–4 digit.")
    return f"{date}_{branch}_{recorder}_{recorder_number}_S{shift}_{activity}"


def create_output_plan(report: VerificationReport, destination: Path | str) -> OutputPlan:
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
            recording.status is not ResultStatus.QR_DECRYPTED
            or recording.trust_level < 1
            or recording.qr is None
            or recording.qr.status is not ResultStatus.QR_DECRYPTED
        ):
            blocked.append(
                f"{recording.recording_id}: {recording.status.value}, trust level {recording.trust_level}; "
                "butuh QR MQ1 yang berhasil didekripsi dan korelasi metadata/video."
            )
            continue
        try:
            name = _operational_name(recording, report)
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
                "Metadata QR terenkripsi MQ1 dipakai untuk melengkapi session.json; pengirim tidak diautentikasi.",
                {
                    "schema": "zyb-recording/v1",
                    "payload": dict(recording.qr.payload or {}),
                    "verification": {
                        "status": recording.qr.status.value,
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
