"""Tests for safe local output preparation."""

from __future__ import annotations

import json
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
from zybtool.output import create_output_plan, execute_output_plan


def _report(source: Path, *, verified: bool = False) -> VerificationReport:
    status = ResultStatus.VERIFIED if verified else ResultStatus.METADATA_ONLY
    qr = (
        QRVerification(
            status=ResultStatus.VERIFIED,
            payload={
                "b": "MM12",
                "r": "Recorder A",
                "dn": "ZY123",
                "sh": 2,
                "a": "BedRoom",
            },
        )
        if verified
        else None
    )
    facts = SessionFacts(
        relative_path="recording_primary_demo",
        kind=UnitKind.FINAL,
        capture_date="2026-11-25",
    )
    recording = RecordingResult(
        recording_id="0123456789abcdef0123456789abcdef",
        unit_paths=("recording_primary_demo",),
        device_id="camera-1",
        created_epoch=None,
        segments=(),
        actual_duration_s=None,
        status=status,
        trust_level=3 if verified else 0,
        qr=qr,
    )
    return VerificationReport(
        source_root=str(source),
        run_id="test-run",
        generated_at="2026-11-25T00:00:00+00:00",
        units=(facts,),
        recordings=(recording,),
    )


def test_metadata_only_output_is_unnamed_and_source_is_preserved(tmp_path: Path) -> None:
    source = tmp_path / "source"
    primary = source / "recording_primary_demo"
    primary.mkdir(parents=True)
    original = primary / "clip.mkv"
    original.write_bytes(b"recording-data")
    (primary / "empty-subfolder").mkdir()
    destination = tmp_path / "ZYB_Output"

    plan = create_output_plan(_report(source), destination)
    assert plan.items[0].folder_name.startswith("_UNNAMED/")
    with pytest.raises(PermissionError):
        execute_output_plan(plan)

    result = execute_output_plan(plan, confirmed=True)
    copied = result / plan.items[0].folder_name / "recording_primary_demo" / "clip.mkv"
    assert copied.read_bytes() == b"recording-data"
    assert (
        result / plan.items[0].folder_name / "recording_primary_demo" / "empty-subfolder"
    ).is_dir()
    assert original.read_bytes() == b"recording-data"
    manifest = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["verification_status"] == "LOCAL_COPY_HASH_VERIFIED_UNSIGNED"
    assert manifest["files"][0]["sha256"]


def test_verified_payload_generates_operational_folder_name(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "recording_primary_demo").mkdir(parents=True)
    plan = create_output_plan(_report(source, verified=True), tmp_path / "ZYB_Output")
    assert plan.items[0].folder_name == "20261125_MM12_Recorder A_ZY123_S2_BedRoom"
    assert plan.items[0].named is True


def test_output_conflict_is_never_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "recording_primary_demo").mkdir(parents=True)
    destination = tmp_path / "ZYB_Output"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        create_output_plan(_report(source), destination)
    assert (destination / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_verified_but_trust_level_two_is_blocked(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "recording_primary_demo").mkdir(parents=True)
    report = _report(source, verified=True)
    recording = report.recordings[0]
    limited = RecordingResult(
        recording_id=recording.recording_id,
        unit_paths=recording.unit_paths,
        device_id=recording.device_id,
        created_epoch=recording.created_epoch,
        segments=recording.segments,
        actual_duration_s=recording.actual_duration_s,
        status=ResultStatus.VERIFIED_WITH_WARNING,
        trust_level=2,
        qr=recording.qr,
    )
    report = VerificationReport(
        source_root=report.source_root,
        run_id=report.run_id,
        generated_at=report.generated_at,
        units=report.units,
        recordings=(limited,),
    )
    plan = create_output_plan(report, tmp_path / "ZYB_Output")
    assert not plan.items
    assert "trust level 2" in plan.blocked[0]
