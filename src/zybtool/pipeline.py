"""Read-only verification pipeline and atomic report output."""

from __future__ import annotations

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
    from metaqr import ReplayLog

    from zybtool.qrscan import verify_recording_qr
    from zybtool.settings import (
        data_dir,
        load_allowlist,
        load_decoder_private_key,
        settings_status,
    )

    settings = settings_status()
    # Trusted-device pairing is optional. Without an allow-list, keep the normal
    # metadata/video verification path running and simply skip cryptographic QR checks.
    if not settings["decoder_key_configured"] or not settings["allowlist_configured"]:
        return recordings

    private_key = load_decoder_private_key()
    allowlist = load_allowlist()
    replay_log = ReplayLog(data_dir() / "replay.jsonl")
    by_path = {unit.facts.relative_path: unit.facts for unit in units}
    verified = []
    for recording in recordings:
        qr = verify_recording_qr(
            recording,
            source,
            private_key=private_key,
            allowlist=allowlist,
            replay_log=replay_log,
        )
        facts = tuple(by_path[path] for path in recording.unit_paths if path in by_path)
        status, level, reasons = evaluate_status(facts, recording.segments, qr=qr)
        verified.append(
            replace(
                recording,
                status=status,
                trust_level=level,
                reasons=reasons,
                qr=qr,
            )
        )
    return tuple(verified)


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
                ResultStatus.UNKNOWN_DEVICE,
                ResultStatus.REPLAY_DETECTED,
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
