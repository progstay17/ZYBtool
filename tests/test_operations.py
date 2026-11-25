from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from zybtool.models import RecordingResult, ResultStatus, SessionFacts, UnitKind, VerificationReport
from zybtool.operations import execute_move_plan, export_excel, undo_move
from zybtool.output import create_output_plan


def _report(source: Path) -> VerificationReport:
    facts = SessionFacts(
        relative_path="recording_primary_demo",
        kind=UnitKind.FINAL,
        device_id="cam-01",
        capture_date="2026-11-25",
        mkv_paths=("recording_primary_demo/stereo/stereo_000001.mkv",),
    )
    recording = RecordingResult(
        recording_id="a" * 32,
        unit_paths=(facts.relative_path,),
        device_id="cam-01",
        created_epoch=None,
        segments=(),
        actual_duration_s=12.5,
        status=ResultStatus.METADATA_ONLY,
        trust_level=0,
        reasons=("QR belum terverifikasi",),
    )
    return VerificationReport(
        source_root=str(source),
        run_id="test-run",
        generated_at="2026-11-25T00:00:00+00:00",
        units=(facts,),
        recordings=(recording,),
    )


def test_move_arrange_and_undo_restore_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    recording = source / "recording_primary_demo"
    stereo = recording / "stereo"
    stereo.mkdir(parents=True)
    (stereo / "stereo_000001.mkv").write_bytes(b"camera-data")
    (stereo / "stereo_000001_imu.csv").write_text("t,x\n1,2\n", encoding="utf-8")
    (recording / "session.json").write_text("{}", encoding="utf-8")
    report = _report(source)
    target = tmp_path / "arranged"
    plan = create_output_plan(report, target)
    try:
        execute_move_plan(plan)
        raise AssertionError("MOVE must require explicit confirmation")
    except PermissionError:
        pass
    moved = execute_move_plan(plan, confirmed=True)
    destination = moved / plan.items[0].folder_name / "recording_primary_demo"
    assert not recording.exists()
    assert (destination / "stereo" / "stereo_000001.mkv").read_bytes() == b"camera-data"
    assert (destination / "stereo" / "stereo_000001_imu.csv").exists()
    assert undo_move(moved) == 1
    assert (recording / "stereo" / "stereo_000001.mkv").read_bytes() == b"camera-data"
    assert not (moved / plan.items[0].folder_name / "recording_primary_demo").exists()


def test_excel_export_has_zyw_sheets_and_preserves_manual_qc(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    report = _report(source)
    workbook_path = tmp_path / "ZYB_Rekap.xlsx"
    export_excel(report, workbook_path)
    workbook = load_workbook(workbook_path)
    assert workbook.sheetnames == ["ZY White", "Cek File", "Scan Audit", "Rekonsiliasi"]
    sheet = workbook["ZY White"]
    sheet.cell(2, 12, "DONE")
    sheet.cell(2, 17, "Supervisor A")
    workbook.save(workbook_path)
    export_excel(report, workbook_path)
    workbook = load_workbook(workbook_path)
    assert workbook["ZY White"].cell(2, 12).value == "DONE"
    assert workbook["ZY White"].cell(2, 17).value == "Supervisor A"
    assert list(tmp_path.glob("ZYB_Rekap.backup-*.xlsx"))
    workbook.close()
