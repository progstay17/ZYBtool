from __future__ import annotations

from pathlib import Path

import pytest

from zybtool.models import (
    QRVerification,
    RecordingResult,
    ResultStatus,
    SessionFacts,
    UnitKind,
    VerificationReport,
)
from zybtool.output import create_output_plan


def _report(source: Path, *, decrypted: bool = False) -> VerificationReport:
    qr = (
        QRVerification(
            status=ResultStatus.QR_DECRYPTED,
            token_version=1,
            payload={"b": "MM12", "r": "Recorder A", "dn": "ZY123", "sh": 2, "a": "BedRoom"},
        )
        if decrypted
        else None
    )
    facts = SessionFacts(
        relative_path="recording_primary_demo", kind=UnitKind.FINAL, capture_date="2026-11-25"
    )
    recording = RecordingResult(
        recording_id="0123456789abcdef0123456789abcdef",
        unit_paths=("recording_primary_demo",),
        device_id="camera-1",
        created_epoch=None,
        segments=(),
        actual_duration_s=None,
        status=ResultStatus.QR_DECRYPTED if decrypted else ResultStatus.METADATA_ONLY,
        trust_level=1 if decrypted else 0,
        qr=qr,
    )
    return VerificationReport(
        source_root=str(source),
        run_id="test-run",
        generated_at="2026-11-25T00:00:00+00:00",
        units=(facts,),
        recordings=(recording,),
    )


def test_metadata_only_plan_is_unnamed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "recording_primary_demo").mkdir(parents=True)
    plan = create_output_plan(_report(source), tmp_path / "ZYB_Output")
    assert plan.items[0].folder_name.startswith("_UNNAMED/")
    assert plan.items[0].named is False


def test_decrypted_payload_generates_operational_folder_name(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "recording_primary_demo").mkdir(parents=True)
    plan = create_output_plan(_report(source, decrypted=True), tmp_path / "ZYB_Output")
    assert plan.items[0].folder_name == "20261125_MM12_Recorder A_ZY123_S2_BedRoom"
    assert plan.items[0].named is True
    assert plan.items[0].qr_metadata is not None


def test_output_conflict_is_never_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "recording_primary_demo").mkdir(parents=True)
    destination = tmp_path / "ZYB_Output"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        create_output_plan(_report(source), destination)
    assert (destination / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_mismatched_payload_is_blocked(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "recording_primary_demo").mkdir(parents=True)
    report = _report(source, decrypted=True)
    original = report.recordings[0]
    limited = RecordingResult(
        recording_id=original.recording_id,
        unit_paths=original.unit_paths,
        device_id=original.device_id,
        created_epoch=original.created_epoch,
        segments=original.segments,
        actual_duration_s=original.actual_duration_s,
        status=ResultStatus.METADATA_MISMATCH,
        trust_level=0,
        qr=original.qr,
    )
    limited_report = VerificationReport(
        source_root=report.source_root,
        run_id=report.run_id,
        generated_at=report.generated_at,
        units=report.units,
        recordings=(limited,),
    )
    plan = create_output_plan(limited_report, tmp_path / "ZYB_Output")
    assert not plan.items
    assert "trust level 0" in plan.blocked[0]
