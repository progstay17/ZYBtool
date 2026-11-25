"""Guarded recording moves, undo journals, and ZYW-style Excel workbooks."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from zybtool.models import ResultStatus, VerificationReport
from zybtool.output import OutputPlan

CREDIT = "Fadhil Ghifarion 法迪 for AIT"
MANUAL_HEADERS = ("Status OSS", "Status Galaxea", "Status HDD", "QC", "Supervisor", "Catatan QC")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_hashes(folder: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for current, dirs, files in os.walk(folder, topdown=True, followlinks=False):
        base = Path(current)
        dirs.sort(key=str.casefold)
        for name in list(dirs):
            child = base / name
            if child.is_symlink():
                raise ValueError(f"Symlink tidak diizinkan: {child}")
        for name in sorted(files, key=str.casefold):
            item = base / name
            if item.is_symlink() or not item.is_file():
                raise ValueError(f"File khusus/symlink tidak diizinkan: {item}")
            result[item.relative_to(folder).as_posix()] = _sha256(item)
    return result


def execute_move_plan(plan: OutputPlan, *, confirmed: bool = False) -> Path:
    """Move source units into a staged output and persist a reversible journal."""
    if not confirmed:
        raise PermissionError("Persetujuan operator wajib diberikan sebelum MOVE.")
    if not plan.items:
        raise ValueError("Tidak ada recording yang memenuhi syarat untuk dipindahkan.")
    source = Path(plan.source_root).resolve(strict=True)
    target = Path(plan.destination).expanduser().resolve()
    if target == source or target in source.parents or source in target.parents:
        raise ValueError("Folder tujuan harus terpisah dari folder sumber.")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise FileExistsError("Folder tujuan tidak kosong; overwrite diblokir.")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.zyb-move-", dir=target.parent))
    moves: list[dict[str, str]] = []
    manifest_files: list[dict[str, Any]] = []
    try:
        for item in plan.items:
            item_root = staging / item.folder_name
            for relative in item.unit_paths:
                original = source if relative == "." else (source / relative).resolve(strict=True)
                if original != source and source not in original.parents:
                    raise ValueError(f"Path recording keluar dari sumber: {relative}")
                if not original.is_dir() or original.is_symlink():
                    raise ValueError(f"Unit sumber bukan folder biasa: {relative}")
                before = _tree_hashes(original)
                destination = item_root if relative == "." else item_root / relative
                if destination.exists():
                    raise FileExistsError(f"Bentrok tujuan MOVE: {destination}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(original), str(destination))
                moves.append({"from": str(original), "to": str(destination)})
                after = _tree_hashes(destination)
                if before != after:
                    raise RuntimeError(f"Hash/struktur berubah saat MOVE: {relative}")
                for rel, digest in sorted(after.items()):
                    file_path = destination / Path(rel)
                    manifest_files.append(
                        {
                            "path": file_path.relative_to(staging).as_posix(),
                            "size_bytes": file_path.stat().st_size,
                            "sha256": digest,
                        }
                    )
                if item.qr_metadata is not None:
                    session_files = sorted(
                        destination.rglob("session.json"), key=lambda p: str(p).casefold()
                    )
                    if not session_files:
                        raise ValueError(f"session.json tidak ditemukan setelah MOVE: {relative}")
                    for session_path in session_files:
                        session = json.loads(session_path.read_text(encoding="utf-8-sig"))
                        if not isinstance(session, dict):
                            raise ValueError(f"session.json bukan object: {session_path}")
                        namespace = session.setdefault("zybtool", {})
                        if not isinstance(namespace, dict) or "qr_metadata" in namespace:
                            raise ValueError(f"Konflik zybtool.qr_metadata: {session_path}")
                        namespace["qr_metadata"] = item.qr_metadata
                        session_path.write_text(
                            json.dumps(session, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                        )
                        relative_session = session_path.relative_to(staging).as_posix()
                        entry = next(
                            row for row in manifest_files if row["path"] == relative_session
                        )
                        entry["sha256"] = _sha256(session_path)
                        entry["size_bytes"] = session_path.stat().st_size
                        entry["metadata_enriched"] = True
        journal_moves = [
            {"from": move["from"], "to": str(target / Path(move["to"]).relative_to(staging))}
            for move in moves
        ]
        journal = {
            "format": "zybtool-move-journal-v1",
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "moves": journal_moves,
            "undone": False,
        }
        output_plan = {
            "format": "zybtool-move-plan-v1",
            "source_root": str(source),
            "destination": str(target),
            "items": [
                {
                    "recording_id": item.recording_id,
                    "folder_name": item.folder_name,
                    "unit_paths": list(item.unit_paths),
                    "named_from_qr": item.named,
                }
                for item in plan.items
            ],
            "blocked": list(plan.blocked),
        }
        (staging / "output_plan.json").write_text(
            json.dumps(output_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (staging / "`move_journal.json`").write_text(
            json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        manifest = {
            "format": "zybtool-move-manifest-v1",
            "verification_status": "MOVE_COMPLETED_HASH_CHECKED_UNSIGNED",
            "qr_protocol": "Metaqr MQ1",
            "qr_sender_authentication": "NONE",
            "trust_level": 1,
            "signature": None,
            "files": manifest_files,
            "blocked": list(plan.blocked),
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if target.exists():
            target.rmdir()
        os.replace(staging, target)
        return target
    except BaseException:
        # Roll back every completed move in reverse order; never overwrite originals.
        for move in reversed(moves):
            old, new = Path(move["from"]), Path(move["to"])
            if new.exists() and not old.exists():
                old.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(new), str(old))
        shutil.rmtree(staging, ignore_errors=True)
        raise


def undo_move(output_folder: Path | str) -> int:
    root = Path(output_folder).resolve(strict=True)
    journal_path = root / "`move_journal.json`"
    if not journal_path.is_file():
        raise FileNotFoundError("Jurnal MOVE tidak ditemukan.")
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    if journal.get("format") != "zybtool-move-journal-v1" or journal.get("undone"):
        raise ValueError("Jurnal MOVE tidak valid atau sudah di-undo.")
    moves = journal.get("moves")
    if not isinstance(moves, list) or not moves:
        raise ValueError("Jurnal tidak berisi perpindahan.")
    for move in moves:
        old, new = Path(move["from"]).resolve(), Path(move["to"]).resolve()
        if root not in new.parents or not new.is_dir() or old.exists():
            raise RuntimeError(f"Undo diblokir karena path berubah/bentrok: {new}")
    completed: list[tuple[Path, Path]] = []
    try:
        for move in reversed(moves):
            old, new = Path(move["from"]), Path(move["to"])
            old.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(new), str(old))
            completed.append((old, new))
    except BaseException:
        for old, new in reversed(completed):
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old), str(new))
        raise
    journal["undone"] = True
    journal["undone_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    journal_path.write_text(
        json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(completed)


def export_excel(report: VerificationReport, path: Path | str) -> Path:
    """Create/update a four-sheet operational workbook, preserving manual QC fields."""
    destination = Path(path).expanduser().resolve()
    if destination.suffix.lower() != ".xlsx":
        raise ValueError("File Excel harus berekstensi .xlsx")
    destination.parent.mkdir(parents=True, exist_ok=True)
    old_manual: dict[str, tuple[Any, ...]] = {}
    if destination.exists():
        backup = destination.with_name(
            f"{destination.stem}.backup-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}{destination.suffix}"
        )
        shutil.copy2(destination, backup)
        existing = load_workbook(destination, read_only=True, data_only=False)
        if "ZY White" in existing.sheetnames:
            sheet = existing["ZY White"]
            headers = [cell.value for cell in sheet[1]]
            key_col = headers.index("Recording ID") + 1 if "Recording ID" in headers else 0
            manual_cols = [
                headers.index(name) + 1 if name in headers else 0 for name in MANUAL_HEADERS
            ]
            if key_col:
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    key = row[key_col - 1]
                    if key:
                        old_manual[str(key)] = tuple(
                            row[col - 1] if col else None for col in manual_cols
                        )
        existing.close()
        wb = load_workbook(destination)
    else:
        wb = Workbook()
        wb.remove(wb.active)
    for name in ("ZY White", "Cek File", "Scan Audit", "Rekonsiliasi"):
        if name in wb.sheetnames:
            del wb[name]
    headers = [
        "Recording ID",
        "Tanggal",
        "Recorder",
        "Device ID",
        "Shift",
        "Aktivitas",
        "Status QR",
        "Trust Level",
        "Segment",
        "Durasi (s)",
        "Source Folder",
        *MANUAL_HEADERS,
    ]
    ws = wb.create_sheet("ZY White")
    ws.append(headers)
    for rec in report.recordings:
        payload = rec.qr.payload if rec.qr and isinstance(rec.qr.payload, dict) else {}
        unit = next((u for u in report.units if u.relative_path in rec.unit_paths), None)
        date = unit.capture_date if unit else ""
        row = [
            rec.recording_id,
            date,
            payload.get("r", ""),
            rec.device_id or "",
            payload.get("sh", ""),
            payload.get("a", ""),
            rec.qr.status.value if rec.qr else "NOT_SCANNED",
            rec.trust_level,
            len(rec.segments),
            rec.actual_duration_s,
            "; ".join(rec.unit_paths),
        ]
        row.extend(old_manual.get(rec.recording_id, (None,) * len(MANUAL_HEADERS)))
        ws.append(row)
    check = wb.create_sheet("Cek File")
    check.append(
        [
            "Recording ID",
            "Recording",
            "Status",
            "Trust",
            "QR Status",
            "Segment",
            "Durasi (s)",
            "Masalah / Alasan",
        ]
    )
    for rec in report.recordings:
        check.append(
            [
                rec.recording_id,
                "; ".join(rec.unit_paths),
                rec.status.value,
                rec.trust_level,
                rec.qr.status.value if rec.qr else "NOT_SCANNED",
                len(rec.segments),
                rec.actual_duration_s,
                " | ".join(rec.reasons),
            ]
        )
    audit = wb.create_sheet("Scan Audit")
    audit.append(
        [
            "Path",
            "Kind",
            "Device",
            "Object ID",
            "Capture Date",
            "MKV",
            "CSV IMU",
            "Missing Files",
            "Warnings",
            "Sync OK",
            "Restart Count",
        ]
    )
    for unit in report.units:
        audit.append(
            [
                unit.relative_path,
                unit.kind.value,
                unit.device_id,
                unit.object_id,
                unit.capture_date,
                len(unit.mkv_paths),
                len(unit.csv_timelines),
                " | ".join(unit.missing_files),
                " | ".join(unit.warnings),
                unit.sync_ok,
                unit.restart_count,
            ]
        )
    recon = wb.create_sheet("Rekonsiliasi")
    recon.append(
        [
            "Recording ID",
            "Folder",
            "Status Scan",
            "QR Token",
            "Sender Authentication",
            "QR First Seen (s)",
            "Payload Recorder",
            "Payload Device",
            "Hasil Korelasi",
            "Catatan",
        ]
    )
    for rec in report.recordings:
        qr = rec.qr
        payload = qr.payload if qr and isinstance(qr.payload, dict) else {}
        recon.append(
            [
                rec.recording_id,
                "; ".join(rec.unit_paths),
                rec.status.value,
                qr.token_id if qr else "",
                "Tidak diautentikasi (MQ1)"
                if qr and qr.status is ResultStatus.QR_DECRYPTED
                else "-",
                qr.time_s if qr else None,
                payload.get("r", ""),
                payload.get("dn", ""),
                "Perlu review" if rec.trust_level < 3 else "Terverifikasi",
                " | ".join(qr.reasons) if qr else "QR belum diverifikasi",
            ]
        )
    for sheet in wb.worksheets:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="244B35")
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for column in sheet.columns:
            letter = get_column_letter(column[0].column)
            width = min(
                55, max(12, max((len(str(c.value or "")) for c in column[:200]), default=10) + 2)
            )
            sheet.column_dimensions[letter].width = width
        sheet.sheet_view.showGridLines = False
    wb.properties.creator = CREDIT
    temp = destination.with_name(destination.name + ".tmp")
    try:
        wb.save(temp)
        os.replace(temp, destination)
    finally:
        if temp.exists():
            temp.unlink()
    return destination
