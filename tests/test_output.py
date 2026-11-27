from __future__ import annotations

from pathlib import Path

from zybtool.models import (
    QRVerification,
    RecordingResult,
    ResultStatus,
    SessionFacts,
    UnitKind,
    VerificationReport,
)
from zybtool.output import create_output_plan


def _report(
    source: Path,
    *,
    decrypted: bool = False,
    payload: dict[str, object] | None = None,
) -> VerificationReport:
    qr = (
        QRVerification(
            status=ResultStatus.QR_DECRYPTED,
            token_version=1,
            payload=payload
            or {"b": "MM12", "r": "Recorder A", "dn": "ZY123", "sh": 2, "a": "BedRoom"},
        )
        if decrypted
        else None
    )
    recording_root = source / "recording_primary_demo"
    total_size_bytes = (
        sum(
            path.stat(follow_symlinks=False).st_size
            for path in recording_root.rglob("*")
            if path.is_file()
        )
        if recording_root.is_dir()
        else 0
    )
    facts = SessionFacts(
        relative_path="recording_primary_demo",
        kind=UnitKind.FINAL,
        capture_date="2026-11-25",
        total_size_bytes=total_size_bytes,
    )
    recording = RecordingResult(
        recording_id="0123456789abcdef0123456789abcdef",
        unit_paths=("recording_primary_demo",),
        device_id="camera-1",
        created_epoch=None,
        segments=(),
        actual_duration_s=None,
        status=ResultStatus.VERIFIED if decrypted else ResultStatus.METADATA_ONLY,
        trust_level=3 if decrypted else 0,
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
    assert plan.items[0].folder_name == "20261125_MM12_RecorderA_ZY123_S2_BedRoom"
    assert plan.items[0].named is True
    assert plan.items[0].qr_metadata is not None


def test_no_shift_arrange_omits_session_token(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "recording_primary_demo").mkdir(parents=True)
    plan = create_output_plan(
        _report(source, decrypted=True),
        tmp_path / "ZYB_Output",
        {"no_shift": True},
    )
    assert plan.items[0].folder_name == "20261125_MM12_RecorderA_ZY123_BedRoom"
    assert "S0" not in plan.items[0].folder_name


def test_arrange_uses_custom_fields_from_native_session_json(tmp_path: Path) -> None:
    source = tmp_path / "source"
    recording = source / "recording_primary_demo"
    recording.mkdir(parents=True)
    (recording / "session.json").write_text(
        '{"capture_date":"2026-11-25","site":{"code":"MM99"},"people":{"name":"Recorder B"}}',
        encoding="utf-8",
    )
    plan = create_output_plan(
        _report(source, decrypted=True),
        tmp_path / "ZYB_Output",
        {
            "template": "{DATE}-{LOCATION_CODE}-{PERSON_NAME}-{DEVICE_ID}-{SESSION}-{ACTIVITY}",
            "field_map": {
                "DATE": "capture_date",
                "LOCATION_CODE": "site.code",
                "PERSON_NAME": "people.name",
            },
        },
    )
    assert plan.items[0].folder_name == "20261125-MM99-RecorderB-ZY123-S2-BedRoom"


def test_output_conflict_is_never_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "recording_primary_demo").mkdir(parents=True)
    destination = tmp_path / "ZYB_Output"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep", encoding="utf-8")
    plan = create_output_plan(_report(source), destination)
    assert plan.items
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


def test_same_operational_key_shares_zyw_group_folder(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "recording_primary_demo").mkdir(parents=True)
    (source / "recording_primary_002").mkdir(parents=True)
    base = _report(source, decrypted=True)
    original = base.recordings[0]
    second = RecordingResult(
        recording_id="fedcba9876543210fedcba9876543210",
        unit_paths=("recording_primary_002",),
        device_id=original.device_id,
        created_epoch=original.created_epoch,
        segments=(),
        actual_duration_s=None,
        status=original.status,
        trust_level=original.trust_level,
        qr=original.qr,
    )
    report = VerificationReport(
        source_root=str(source),
        run_id="two-recordings",
        generated_at=base.generated_at,
        units=(
            base.units[0],
            SessionFacts(
                relative_path="recording_primary_002",
                kind=UnitKind.FINAL,
                capture_date="2026-11-25",
            ),
        ),
        recordings=(original, second),
    )
    plan = create_output_plan(report, tmp_path / "ZYB_Output")
    assert len(plan.items) == 2
    assert {item.folder_name for item in plan.items} == {"20261125_MM12_RecorderA_ZY123_S2_BedRoom"}


def test_corrupted_recording_is_separated_into_rejected_group(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "recording_primary_demo").mkdir(parents=True)
    base = _report(source)
    original = base.recordings[0]
    corrupted = RecordingResult(
        recording_id=original.recording_id,
        unit_paths=original.unit_paths,
        device_id=original.device_id,
        created_epoch=original.created_epoch,
        segments=original.segments,
        actual_duration_s=original.actual_duration_s,
        status=ResultStatus.CORRUPTED,
        trust_level=0,
        reasons=("Corrupted media",),
    )
    report = VerificationReport(
        source_root=base.source_root,
        run_id=base.run_id,
        generated_at=base.generated_at,
        units=base.units,
        recordings=(corrupted,),
    )
    plan = create_output_plan(report, tmp_path / "ZYB_Output")
    assert plan.items[0].folder_name == "_REJECTED"


def test_arrange_maps_profile_defined_aitqr_short_keys(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "recording_primary_demo").mkdir(parents=True)
    payload = {
        "p": "zyb-recording",
        "pv": 1,
        "s": "3F30WDDZWKDYPZJD",
        "c": "testing",
        "d": "ZY007",
        "l": "MM3201",
        "m": "test only",
        "ss": "5",
        "t": "Kitchen",
    }
    plan = create_output_plan(
        _report(source, decrypted=True, payload=payload),
        tmp_path / "ZYB_Output",
        {
            "field_map": {
                "LOCATION_CODE": "qr.l",
                "PERSON_NAME": "qr.m",
                "DEVICE_ID": "qr.d",
                "SESSION": "qr.ss",
                "ACTIVITY": "qr.t",
            }
        },
    )
    assert len(plan.items) == 1
    assert plan.items[0].folder_name == "20261125_MM3201_testonly_ZY007_S5_Kitchen"
    assert plan.items[0].named is True


def test_verified_with_capture_warning_is_still_named_from_decrypted_qr(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "recording_primary_demo").mkdir(parents=True)
    base = _report(source, decrypted=True)
    original = base.recordings[0]
    warning_recording = RecordingResult(
        recording_id=original.recording_id,
        unit_paths=original.unit_paths,
        device_id=original.device_id,
        created_epoch=original.created_epoch,
        segments=original.segments,
        actual_duration_s=original.actual_duration_s,
        status=ResultStatus.VERIFIED_WITH_WARNING,
        trust_level=2,
        reasons=("session_sync quality warning",),
        qr=original.qr,
    )
    report = VerificationReport(
        source_root=base.source_root,
        run_id=base.run_id,
        generated_at=base.generated_at,
        units=base.units,
        recordings=(warning_recording,),
    )

    plan = create_output_plan(report, tmp_path / "ZYB_Output")

    assert len(plan.items) == 1
    assert plan.items[0].folder_name == "20261125_MM12_RecorderA_ZY123_S2_BedRoom"
    assert plan.items[0].named is True


def test_excel_groups_by_qr_ss_and_counts_each_recording_once(tmp_path: Path) -> None:
    from openpyxl import load_workbook

    from zybtool.models import Segment, VideoEvidence
    from zybtool.operations import export_excel

    source = tmp_path / "source"
    first_root = source / "recording_primary_demo"
    second_root = source / "recording_primary_second"
    first_camera = first_root / "stereo"
    second_camera = second_root / "stereo"
    first_camera.mkdir(parents=True)
    second_camera.mkdir(parents=True)
    (first_camera / "video.mkv").write_bytes(b"a" * 100)
    (first_root / "session.json").write_bytes(b"12345")
    (second_camera / "video.mkv").write_bytes(b"b" * 200)
    (second_root / "meta.json").write_bytes(b"12345678")
    payload = {"c": "Fadhil", "d": "ZY009", "l": "MM3208", "ss": "3", "t": "Bedroom"}
    base = _report(source, decrypted=True, payload=payload)
    original = base.recordings[0]

    def segment(path: str, size: int) -> Segment:
        return Segment(
            unit_path=path,
            camera="stereo",
            video=VideoEvidence(
                relative_path=f"{path}/stereo/video.mkv",
                size_bytes=size,
                packet_count=10,
                pts_first_s=0.0,
                pts_last_s=9.0,
                duration_s=10.0,
                frame_rate=30.0,
                pts_monotonic=True,
                keyframes=1,
            ),
        )

    first = RecordingResult(
        recording_id=original.recording_id,
        unit_paths=("recording_primary_demo",),
        device_id=original.device_id,
        created_epoch=original.created_epoch,
        segments=(segment("recording_primary_demo", 100),),
        actual_duration_s=3600.0,
        status=original.status,
        trust_level=original.trust_level,
        qr=original.qr,
    )
    second = RecordingResult(
        recording_id="fedcba9876543210fedcba9876543210",
        unit_paths=("recording_primary_second",),
        device_id=original.device_id,
        created_epoch=original.created_epoch,
        segments=(segment("recording_primary_second", 200),),
        actual_duration_s=1800.0,
        status=original.status,
        trust_level=original.trust_level,
        qr=original.qr,
    )
    report = VerificationReport(
        source_root=str(source),
        run_id="excel-group-test",
        generated_at=base.generated_at,
        units=(
            base.units[0],
            SessionFacts(
                relative_path="recording_primary_second",
                kind=UnitKind.FINAL,
                capture_date="2026-11-25",
                total_size_bytes=sum(
                    path.stat(follow_symlinks=False).st_size
                    for path in second_root.rglob("*")
                    if path.is_file()
                ),
            ),
        ),
        recordings=(first, second),
    )

    path = export_excel(report, tmp_path / "report.xlsx")
    workbook = load_workbook(path, data_only=True)
    sheet = workbook["ZY White"]
    headers = [cell.value for cell in sheet[1]]
    row = {name: sheet.cell(2, index + 1).value for index, name in enumerate(headers)}

    assert sheet.max_row == 2
    assert row["Recorder"] == "Fadhil"
    assert row["Device ID"] == "ZY009"
    assert row["Lokasi"] == "MM3208"
    assert row["Shift"] == "3"
    assert row["Aktivitas"] == "Bedroom"
    assert row["Jumlah Sesi"] == 2
    assert row["Durasi"].total_seconds() == 5_400
    assert row["Total Data"] == 313 / 1_000_000_000
    assert "Qualified" not in " ".join(str(value) for value in headers)
    assert "Rejected" not in " ".join(str(value) for value in headers)
    workbook.close()

    workbook = load_workbook(path)
    sheet = workbook["ZY White"]
    qc_col = headers.index("QC") + 1
    sheet.cell(2, qc_col, "QC OK")
    workbook.save(path)
    workbook.close()

    export_excel(report, path)
    workbook = load_workbook(path, data_only=True)
    assert workbook["ZY White"].cell(2, qc_col).value == "QC OK"
    workbook.close()
