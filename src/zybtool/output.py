"""Safe local output planning and copy with source preservation and SHA-256 checks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
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


@dataclass(frozen=True, slots=True)
class OutputPlan:
    source_root: str
    destination: str
    items: tuple[OutputItem, ...]
    blocked: tuple[str, ...]


def _safe_component(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field AITQR '{field}' kosong.")
    result = value.strip()
    if result in {".", ".."} or re.search(r'[<>:"/\\|?*\x00-\x1f]', result):
        raise ValueError(f"Field AITQR '{field}' mengandung karakter nama folder yang tidak aman.")
    if result.endswith((".", " ")):
        raise ValueError(f"Field AITQR '{field}' tidak boleh diakhiri titik atau spasi.")
    if result.upper().split(".")[0] in {
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
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(
            "Folder output harus belum ada atau kosong; overwrite tidak diizinkan."
        )

    items: list[OutputItem] = []
    blocked: list[str] = []
    for recording in report.recordings:
        if not recording.unit_paths:
            blocked.append(f"{recording.recording_id}: tidak memiliki folder sumber.")
            continue
        if recording.status is ResultStatus.METADATA_ONLY:
            items.append(
                OutputItem(
                    recording.recording_id,
                    f"_UNNAMED/{recording.recording_id[:16]}",
                    recording.unit_paths,
                    recording.status.value,
                    False,
                    "Tidak ada QR tepercaya; perlu keputusan operator.",
                )
            )
            continue
        if (
            recording.status is not ResultStatus.VERIFIED
            or recording.trust_level < 3
            or recording.qr is None
            or recording.qr.status is not ResultStatus.VERIFIED
        ):
            blocked.append(
                f"{recording.recording_id}: {recording.status.value}, trust level {recording.trust_level}; "
                "butuh QR terverifikasi dan korelasi level 3 atau lebih."
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
                "Nama dibuat dari payload QR yang terverifikasi.",
            )
        )

    names = [item.folder_name.casefold() for item in items]
    if len(names) != len(set(names)):
        raise ValueError("Ada bentrokan nama output; tidak ada suffix otomatis yang ditambahkan.")
    return OutputPlan(str(source), str(target), tuple(items), tuple(blocked))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_file_verified(
    source: Path, destination: Path, manifest: list[dict[str, Any]], relative: str
) -> None:
    if destination.exists():
        raise FileExistsError(f"Tujuan file sudah ada; overwrite diblokir: {destination}")
    before = _sha256(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    copied = _sha256(destination)
    after = _sha256(source)
    if before != copied or before != after:
        raise RuntimeError(f"SHA-256 tidak cocok atau sumber berubah saat disalin: {relative}")
    manifest.append(
        {
            "path": relative.replace("\\", "/"),
            "size_bytes": destination.stat().st_size,
            "sha256": copied,
        }
    )


def _copy_unit(
    source_root: Path, relative_unit: str, destination_root: Path, manifest: list[dict[str, Any]]
) -> None:
    candidate = (
        source_root if relative_unit == "." else Path(os.path.abspath(source_root / relative_unit))
    )
    if candidate != source_root and source_root not in candidate.parents:
        raise ValueError(f"Path unit keluar dari folder sumber: {relative_unit}")
    if relative_unit != ".":
        current_path_check = candidate
        while current_path_check != source_root:
            if current_path_check.is_symlink():
                raise ValueError(f"Symlink tidak diizinkan pada path sumber: {current_path_check}")
            current_path_check = current_path_check.parent
    unit = candidate.resolve(strict=True)
    if unit != source_root and source_root not in unit.parents:
        raise ValueError(f"Path unit keluar dari folder sumber: {relative_unit}")
    if not unit.is_dir():
        raise ValueError(f"Unit sumber bukan folder biasa: {relative_unit}")
    for current, dirs, files in os.walk(unit, topdown=True, followlinks=False):
        current_path = Path(current)
        relative_directory = current_path.relative_to(unit)
        if relative_unit == ".":
            target_directory = destination_root / relative_directory
        else:
            target_directory = destination_root / relative_unit / relative_directory
        target_directory.mkdir(parents=True, exist_ok=True)
        for name in list(dirs):
            candidate = current_path / name
            if candidate.is_symlink():
                raise ValueError(f"Symlink tidak diizinkan pada output: {candidate}")
            child_relative = candidate.relative_to(unit)
            if relative_unit == ".":
                child_target = destination_root / child_relative
            else:
                child_target = destination_root / relative_unit / child_relative
            child_target.mkdir(parents=True, exist_ok=True)
        for name in files:
            source_file = current_path / name
            if source_file.is_symlink() or not source_file.is_file():
                raise ValueError(f"File khusus/symlink tidak diizinkan: {source_file}")
            relative_inside = source_file.relative_to(unit)
            if relative_unit == ".":
                target_file = destination_root / relative_inside
            else:
                target_file = destination_root / relative_unit / relative_inside
            relative_target = target_file.relative_to(destination_root.parent).as_posix()
            _copy_file_verified(source_file, target_file, manifest, relative_target)


def execute_output_plan(plan: OutputPlan, *, confirmed: bool = False) -> Path:
    if not confirmed:
        raise PermissionError("Persetujuan operator wajib diberikan sebelum penyalinan.")
    if not plan.items:
        raise ValueError("Tidak ada recording yang memenuhi syarat untuk disalin.")
    source = Path(plan.source_root).resolve(strict=True)
    target = Path(plan.destination).expanduser().resolve()
    if target == source or target in source.parents or source in target.parents:
        raise ValueError("Folder output harus terpisah dari folder sumber.")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise FileExistsError("Folder output tidak kosong atau bukan folder; overwrite diblokir.")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.zyb-", dir=target.parent))
    manifest: list[dict[str, Any]] = []
    try:
        for item in plan.items:
            item_root = staging / item.folder_name
            for relative in item.unit_paths:
                _copy_unit(source, relative, item_root, manifest)
        document = {
            "format": "zybtool-local-output-manifest-v1",
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "source_root": str(source),
            "verification_status": "LOCAL_COPY_HASH_VERIFIED_UNSIGNED",
            "signature": None,
            "items": [
                {
                    "recording_id": item.recording_id,
                    "folder_name": item.folder_name,
                    "status": item.status,
                    "named_from_qr": item.named,
                    "reason": item.reason,
                    "unit_paths": list(item.unit_paths),
                }
                for item in plan.items
            ],
            "files": manifest,
            "blocked": list(plan.blocked),
        }
        (staging / "manifest.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if target.exists():
            if any(target.iterdir()):
                raise FileExistsError("Folder output berubah dan sekarang tidak kosong.")
            target.rmdir()
        os.replace(staging, target)
        return target
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
