"""Read-only verification pipeline and atomic report output."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from zybtool.discovery import discover_units
from zybtool.grouper import group_recordings
from zybtool.models import (
    Finding,
    RecordingResult,
    ResultStatus,
    Unit,
    UnitKind,
    VerificationReport,
)
from zybtool.report import report_csv, report_dict, report_html, report_json
from zybtool.status import evaluate_status
from zybtool.util import atomic_write, stable_run_id
from zybtool.videoscan import scan_video


def _verify_qr_if_configured(
    recordings: tuple[RecordingResult, ...],
    units: tuple[Unit, ...],
    source: Path,
) -> tuple[RecordingResult, ...]:
    from zybtool.qrscan import verify_recording_qr
    from zybtool.settings import load_decoder_private_key, settings_status

    settings = settings_status()
    private_key = load_decoder_private_key() if settings["decoder_key_configured"] else None
    by_path = {unit.facts.relative_path: unit.facts for unit in units}
    results = []
    for recording in recordings:
        qr = verify_recording_qr(recording, source, private_key=private_key)
        facts = tuple(by_path[path] for path in recording.unit_paths if path in by_path)
        status, level, reasons = evaluate_status(facts, recording.segments, qr=qr)
        results.append(replace(recording, status=status, trust_level=level, reasons=reasons, qr=qr))
    return tuple(results)


def _natural_path_key(value: str) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)
    )


def _inherit_standalone_qr(
    recordings: tuple[RecordingResult, ...],
    units: tuple[Unit, ...],
) -> tuple[RecordingResult, ...]:
    """Assign QR-less standalone folders to the most recent preceding QR folder by name."""
    by_path = {unit.facts.relative_path: unit.facts for unit in units}
    standalone = sorted(
        (
            item
            for item in recordings
            if any(
                by_path.get(path) and by_path[path].standalone_stereo for path in item.unit_paths
            )
        ),
        key=lambda item: _natural_path_key(item.unit_paths[0]),
    )
    other = [item for item in recordings if item not in standalone]
    output: list[RecordingResult] = []
    pending: list[RecordingResult] = []
    active_qr = None

    def flush() -> None:
        nonlocal pending
        if not pending:
            return
        members = pending
        pending = []
        facts = tuple(
            by_path[path] for item in members for path in item.unit_paths if path in by_path
        )
        segments = tuple(segment for item in members for segment in item.segments)
        qr = active_qr
        status, level, reasons = evaluate_status(facts, segments, qr=qr)
        first = members[0]
        durations: dict[str, float] = {}
        for segment in segments:
            if segment.video.duration_s is not None:
                durations[segment.camera] = (
                    durations.get(segment.camera, 0.0) + segment.video.duration_s
                )
        output.append(
            replace(
                first,
                unit_paths=tuple(path for item in members for path in item.unit_paths),
                segments=segments,
                actual_duration_s=max(durations.values()) if durations else None,
                status=status,
                trust_level=level,
                reasons=reasons,
                qr=qr,
            )
        )

    for item in standalone:
        qr = item.qr
        qr_is_absent = qr is None or (
            qr.status is ResultStatus.QR_MISSING
            and any(reason.startswith("Tidak ada QR terenkripsi") for reason in qr.reasons)
        )
        if not qr_is_absent:
            # A visible but invalid/unreadable QR is still a boundary: never
            # let later chunks accidentally inherit the previous recording ID.
            if pending:
                flush()
            active_qr = qr
            pending = [item]
        elif active_qr is not None:
            pending.append(item)
        else:
            # Before the first QR there is no trustworthy identity to inherit.
            output.append(item)
    flush()
    return tuple(
        sorted(
            (*other, *output),
            key=lambda item: (item.device_id or "", item.created_epoch or 0, item.recording_id),
        )
    )


def run_verification(
    source_root: Path | str,
    *,
    allow_missing_media: bool = False,
) -> VerificationReport:
    source = Path(source_root).expanduser().resolve(strict=True)
    units = discover_units(source)
    evidence = {}
    relative_paths = [unit.facts.relative_path for unit in units]

    for unit in units:
        # Live/partial units are already INCOMPLETE; avoid expensive full demux
        # until they have the final sidecars required for trustworthy correlation.
        if unit.facts.kind is not UnitKind.FINAL:
            continue
        for relative in unit.facts.mkv_paths:
            path = (unit.path / Path(relative)).resolve(strict=True)
            relative_video = (
                Path(unit.facts.relative_path) / Path(relative)
                if unit.facts.relative_path != "."
                else Path(relative)
            ).as_posix()
            video = scan_video(path, relative_video)
            evidence[str(path)] = video
            relative_paths.append(relative_video)

    recordings = group_recordings(
        units,
        evidence,
        allow_missing_media=allow_missing_media,
    )
    recordings = _verify_qr_if_configured(recordings, units, source)
    recordings = _inherit_standalone_qr(recordings, units)

    findings = tuple(
        Finding(
            code=item.status,
            severity="error"
            if item.status
            in {
                ResultStatus.INCOMPLETE,
                ResultStatus.CORRUPTED,
                ResultStatus.METADATA_MISMATCH,
                ResultStatus.AMBIGUOUS,
                ResultStatus.QR_MISSING,
                ResultStatus.INVALID_SIGNATURE,
                ResultStatus.QR_DECRYPT_FAILED,
            }
            else "info",
            subject=item.recording_id,
            message="; ".join(item.reasons) or item.status.value,
            evidence=item.unit_paths,
        )
        for item in recordings
    )
    return VerificationReport(
        source_root=str(source),
        run_id=stable_run_id(source, relative_paths),
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        units=tuple(unit.facts for unit in units),
        recordings=recordings,
        findings=findings,
    )


def write_report(report: VerificationReport, output_root: Path | str) -> Path:
    source = Path(report.source_root).resolve(strict=True)
    output = Path(output_root).expanduser().resolve()
    if output == source or output in source.parents or source in output.parents:
        raise ValueError("Folder laporan harus terpisah dari folder sumber read-only")
    destination = output / report.run_id
    destination.mkdir(parents=True, exist_ok=True)

    payload = report_dict(report)
    inventory = {
        "source_root": report.source_root,
        "run_id": report.run_id,
        "units": payload["units"],
    }
    groups = {
        "run_id": report.run_id,
        "recordings": payload["recordings"],
    }
    atomic_write(destination / "inventory.json", _json_bytes(inventory))
    atomic_write(destination / "groups.json", _json_bytes(groups))
    atomic_write(destination / "report.json", report_json(report))
    atomic_write(destination / "report.csv", report_csv(report))
    atomic_write(destination / "report.html", report_html(report))
    return destination


def _json_bytes(value: object) -> bytes:
    from zybtool.util import canonical_json_bytes

    return canonical_json_bytes(value) + b"\n"
