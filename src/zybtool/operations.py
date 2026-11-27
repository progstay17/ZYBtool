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
    """Move recording units into reusable ZYW-style groups; persist a per-run undo journal."""
    if not confirmed:
        raise PermissionError("Persetujuan operator wajib diberikan sebelum MOVE.")
    if not plan.items:
        raise ValueError("Tidak ada recording yang memenuhi syarat untuk dipindahkan.")
    source = Path(plan.source_root).resolve(strict=True)
    target = Path(plan.destination).expanduser().resolve()
    if target == source or target in source.parents or source in target.parents:
        raise ValueError("Folder tujuan harus terpisah dari folder sumber.")
    if target.exists() and not target.is_dir():
        raise FileExistsError("Path Organized Folders bukan folder.")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.zyb-move-", dir=target.parent))
    staged_moves: list[dict[str, str]] = []
    final_moves: list[dict[str, str]] = []
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
                staged_destination = item_root if relative == "." else item_root / relative
                if staged_destination.exists():
                    raise FileExistsError(
                        f"Bentrok path recording di staging: {staged_destination}"
                    )
                staged_destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(original), str(staged_destination))
                staged_moves.append({"from": str(original), "to": str(staged_destination)})
                after = _tree_hashes(staged_destination)
                if before != after:
                    raise RuntimeError(f"Hash/struktur berubah saat MOVE: {relative}")
                if item.qr_metadata is not None:
                    session_files = sorted(
                        staged_destination.rglob("session.json"), key=lambda p: str(p).casefold()
                    )
                    if not session_files:
                        raise ValueError(f"session.json tidak ditemukan setelah MOVE: {relative}")
                    for session_path in session_files:
                        session = json.loads(session_path.read_text(encoding="utf-8-sig"))
                        if not isinstance(session, dict):
                            raise ValueError(f"session.json bukan object: {session_path}")
                        namespace = session.setdefault("zybtool", {})
                        if not isinstance(namespace, dict):
                            raise ValueError(
                                f"Konflik namespace zybtool pada session.json: {session_path}"
                            )
                        existing_metadata = namespace.get("qr_metadata")
                        if existing_metadata is not None:
                            if not isinstance(existing_metadata, dict):
                                raise ValueError(
                                    f"Konflik zybtool.qr_metadata (format lama tidak valid): {session_path}"
                                )
                            # Same QR payload is safe to re-arrange. Refresh verification
                            # details after software updates, preserving unrelated metadata.
                            if existing_metadata.get("schema") != item.qr_metadata.get(
                                "schema"
                            ) or existing_metadata.get("payload") != item.qr_metadata.get(
                                "payload"
                            ):
                                raise ValueError(
                                    f"Konflik zybtool.qr_metadata: payload QR yang sudah ada berbeda "
                                    f"dengan QR recording ini ({session_path})"
                                )
                            merged_metadata = dict(existing_metadata)
                            merged_metadata.update(item.qr_metadata)
                            if merged_metadata != existing_metadata:
                                namespace["qr_metadata"] = merged_metadata
                                session_path.write_text(
                                    json.dumps(session, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8",
                                )
                        else:
                            namespace["qr_metadata"] = item.qr_metadata
                            session_path.write_text(
                                json.dumps(session, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8",
                            )
                for rel, digest in sorted(_tree_hashes(staged_destination).items()):
                    file_path = staged_destination / Path(rel)
                    manifest_files.append(
                        {
                            "path": (
                                Path(item.folder_name) / Path(relative) / Path(rel)
                            ).as_posix(),
                            "size_bytes": file_path.stat().st_size,
                            "sha256": digest,
                        }
                    )
        # Merge each staged unit into the persistent Organized Folders root.
        # Existing group folders are reused; existing session paths are never overwritten.
        for move in staged_moves:
            staged_path = Path(move["to"])
            final_path = target / staged_path.relative_to(staging)
            if final_path.exists():
                raise FileExistsError(f"Bentrok tujuan MOVE (tidak ada overwrite): {final_path}")
            expected_hashes = _tree_hashes(staged_path)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged_path), str(final_path))
            final_moves.append({"from": move["from"], "to": str(final_path)})
            if _tree_hashes(final_path) != expected_hashes:
                raise RuntimeError(f"Verifikasi hash gagal setelah MOVE: {final_path}")
        run_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        run_dir = target / ".zybtool" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
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
        journal = {
            "format": "zybtool-move-journal-v1",
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "moves": final_moves,
            "undone": False,
        }
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
        (run_dir / "output_plan.json").write_text(
            json.dumps(output_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (run_dir / "move_journal.json").write_text(
            json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return target
    except BaseException:
        # Restore every completed move, including items already merged into Organized Folders.
        for move in reversed(final_moves):
            old, new = Path(move["from"]), Path(move["to"])
            if new.exists() and not old.exists():
                old.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(new), str(old))
        for move in reversed(staged_moves):
            old, staged = Path(move["from"]), Path(move["to"])
            if staged.exists() and not old.exists():
                old.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(staged), str(old))
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def undo_move(output_folder: Path | str) -> int:
    root = Path(output_folder).resolve(strict=True)
    run_journals = (
        sorted(
            (root / ".zybtool" / "runs").glob("*/move_journal.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if (root / ".zybtool" / "runs").is_dir()
        else []
    )
    journal_path = next(
        (
            path
            for path in run_journals
            if path.is_file() and not json.loads(path.read_text(encoding="utf-8")).get("undone")
        ),
        root / "move_journal.json",
    )
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


def _excel_group_key(values: tuple[Any, ...]) -> str:
    """Stable identity for one recorder/date/activity/location/QR-shift group."""
    return json.dumps(
        [str(value or "") for value in values], ensure_ascii=False, separators=(",", ":")
    )


def export_excel(report: VerificationReport, path: Path | str) -> Path:
    """Export one row per QR-defined operational group; never infer or split shifts."""
    destination = Path(path).expanduser().resolve()
    if destination.suffix.lower() != ".xlsx":
        raise ValueError("File Excel harus berekstensi .xlsx")
    destination.parent.mkdir(parents=True, exist_ok=True)

    old_manual_by_group: dict[str, tuple[Any, ...]] = {}
    old_manual_by_recording: dict[str, tuple[Any, ...]] = {}
    if destination.exists():
        backup = destination.with_name(
            f"{destination.stem}.backup-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}{destination.suffix}"
        )
        shutil.copy2(destination, backup)
        existing = load_workbook(destination, read_only=True, data_only=False)
        if "ZY White" in existing.sheetnames:
            sheet = existing["ZY White"]
            headers = [cell.value for cell in sheet[1]]
            manual_cols = [
                headers.index(name) if name in headers else -1 for name in MANUAL_HEADERS
            ]
            group_col = headers.index("Group Key") if "Group Key" in headers else -1
            id_col = headers.index("Recording ID") if "Recording ID" in headers else -1
            for row in sheet.iter_rows(min_row=2, values_only=True):
                manual = tuple(row[col] if col >= 0 and col < len(row) else None for col in manual_cols)
                if group_col >= 0 and group_col < len(row) and row[group_col]:
                    old_manual_by_group[str(row[group_col])] = manual
                if id_col >= 0 and id_col < len(row) and row[id_col]:
                    for recording_id in str(row[id_col]).split("; "):
                        old_manual_by_recording[recording_id] = manual
        existing.close()
        wb = load_workbook(destination)
    else:
        wb = Workbook()
        wb.remove(wb.active)

    for name in ("ZY White", "Cek File", "Scan Audit", "Rekonsiliasi"):
        if name in wb.sheetnames:
            del wb[name]

    groups: dict[tuple[str, ...], dict[str, Any]] = {}
    for rec in report.recordings:
        payload = rec.qr.payload if rec.qr and isinstance(rec.qr.payload, dict) else {}
        unit = next((u for u in report.units if u.relative_path in rec.unit_paths), None)
        date = str((unit.capture_date if unit else "") or "")
        # QR payload is the source of truth for these fields. In particular, ss
        # is copied verbatim; recording timestamps never reassign a shift.
        values = (
            str(payload.get("d") or rec.device_id or ""),
            date,
            str(payload.get("t") or ""),
            str(payload.get("l") or ""),
            str(payload.get("ss") or ""),
            str(payload.get("c") or ""),
        )
        group = groups.setdefault(
            values,
            {
                "recording_ids": [],
                "folders": [],
                "duration_s": 0.0,
                "size_bytes": 0,
                "segments": 0,
                "qr_statuses": [],
                "trust_levels": [],
            },
        )
        group["recording_ids"].append(rec.recording_id)
        group["folders"].extend(rec.unit_paths)
        group["duration_s"] += float(rec.actual_duration_s or 0.0)
        group["size_bytes"] += sum(max(0, int(segment.video.size_bytes)) for segment in rec.segments)
        group["segments"] += len(rec.segments)
        group["qr_statuses"].append(rec.qr.status.value if rec.qr else "NOT_SCANNED")
        group["trust_levels"].append(rec.trust_level)

    headers = [
        "Device ID", "Tanggal", "Aktivitas", "Lokasi", "Shift", "Recorder",
        "Durasi (jam)", "Jumlah Sesi", "Total Data (GB)", "Jumlah Segment",
        "Status QR", "Trust Level", "Source Folder", "Recording ID",
        *MANUAL_HEADERS, "Group Key",
    ]
    ws = wb.create_sheet("ZY White")
    ws.append(headers)
    for values, group in sorted(groups.items(), key=lambda item: tuple(str(v).casefold() for v in item[0])):
        key = _excel_group_key(values)
        manual = old_manual_by_group.get(key)
        if manual is None:
            legacy = [old_manual_by_recording.get(recording_id) for recording_id in group["recording_ids"]]
            present = [value for value in legacy if value is not None]
            manual = present[0] if present and all(value == present[0] for value in present) else (None,) * len(MANUAL_HEADERS)
        row = [
            *values,
            group["duration_s"] / 3600,
            len(group["recording_ids"]),
            group["size_bytes"] / 1_000_000_000,
            group["segments"],
            "; ".join(sorted(set(group["qr_statuses"]))),
            min(group["trust_levels"]) if group["trust_levels"] else 0,
            "; ".join(sorted(set(group["folders"]))),
            "; ".join(group["recording_ids"]),
            *manual,
            key,
        ]
        ws.append(row)
    ws.column_dimensions[get_column_letter(len(headers))].hidden = True

    check = wb.create_sheet("Cek File")
    check.append(
        ["Recording ID", "Recording", "Status", "Trust", "QR Status", "Segment",
         "Durasi (s)", "Ukuran (bytes)", "Masalah / Alasan"]
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
                sum(max(0, int(segment.video.size_bytes)) for segment in rec.segments),
                " | ".join(rec.reasons),
            ]
        )

    audit = wb.create_sheet("Scan Audit")
    audit.append(
        ["Path", "Kind", "Device", "Object ID", "Capture Date", "MKV", "CSV IMU",
         "Missing Files", "Warnings", "Sync OK", "Restart Count"]
    )
    for unit in report.units:
        audit.append(
            [
                unit.relative_path, unit.kind.value, unit.device_id, unit.object_id,
                unit.capture_date, len(unit.mkv_paths), len(unit.csv_timelines),
                " | ".join(unit.missing_files), " | ".join(unit.warnings),
                unit.sync_ok, unit.restart_count,
            ]
        )

    recon = wb.create_sheet("Rekonsiliasi")
    recon.append(
        ["Recording ID", "Folder", "Status Scan", "QR Token", "QR Encryption",
         "QR First Seen (s)", "Payload Recorder", "Payload Device", "Payload Location",
         "Payload Shift", "Payload Activity", "Hasil Korelasi", "Catatan"]
    )
    for rec in report.recordings:
        qr = rec.qr
        payload = qr.payload if qr and isinstance(qr.payload, dict) else {}
        recon.append(
            [
                rec.recording_id, "; ".join(rec.unit_paths), rec.status.value,
                qr.token_id if qr else "",
                "MQ1 encrypted" if qr and qr.status is ResultStatus.QR_DECRYPTED else "-",
                qr.time_s if qr else None,
                payload.get("c", ""), payload.get("d", ""), payload.get("l", ""),
                payload.get("ss", ""), payload.get("t", ""),
                "Perlu review" if rec.status is not ResultStatus.VERIFIED or rec.trust_level < 3
                else "Terverifikasi",
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
    except PermissionError:
        raise PermissionError(
            f"File Excel sedang dibuka. Tutup dulu lalu export ulang:\n{destination}"
        ) from None
    finally:
        if temp.exists():
            temp.unlink()
    return destination
