from pathlib import Path

from zybtool.discovery import discover_units
from zybtool.grouper import group_recordings
from zybtool.models import (
    CsvTimeline,
    ResultStatus,
    SessionFacts,
    Unit,
    UnitKind,
    VideoEvidence,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_sample2_live_recordings_are_not_merged_across_devices() -> None:
    units = discover_units(FIXTURES)
    results = group_recordings(units, {}, allow_missing_media=True)

    assert len(results) == 4
    by_path = {path: result for result in results for path in result.unit_paths}
    primary = by_path["sample2_primary/recording_primary_fixture-002_20250210_123913_01"]
    live_a = by_path["sample2_live/.live_20250209_091607"]
    live_b = by_path["sample2_live/.live_20250210_174436"]

    assert primary.status is ResultStatus.METADATA_ONLY
    assert live_a.status is ResultStatus.INCOMPLETE
    assert live_b.status is ResultStatus.INCOMPLETE
    assert primary.device_id == "fixture-device-002"
    assert live_a.device_id == live_b.device_id == "fixture-device-003"
    assert primary.unit_paths == (
        "sample2_primary/recording_primary_fixture-002_20250210_123913_01",
    )


def test_metadata_only_can_never_become_verified() -> None:
    units = discover_units(FIXTURES)
    results = group_recordings(units, {}, allow_missing_media=True)

    assert all(item.status is not ResultStatus.VERIFIED for item in results)
    assert all(item.trust_level == 0 for item in results)


def _standalone_unit(root: Path, name: str, created: float, duration: float) -> Unit:
    path = root / name
    facts = SessionFacts(
        relative_path=name,
        kind=UnitKind.FINAL,
        capture_date="2026-11-26",
        created_epoch=created,
        standalone_stereo=True,
        sync_wall_s=duration,
        sync_ok=True,
        has_stop_log=True,
        mkv_paths=("stereo/stereo_000.mkv",),
        csv_timelines=(CsvTimeline("stereo/stereo_000000_imu_frametimes.csv", 0, 1_000_000, 2),),
    )
    return Unit(path, facts)


def test_standalone_continuations_are_grouped_when_capture_gaps_are_short(tmp_path: Path) -> None:
    units = (
        _standalone_unit(tmp_path, "recording_stereo_223827", 1000.0, 452.0),
        _standalone_unit(tmp_path, "recording_stereo_224616", 1469.0, 387.0),
        _standalone_unit(tmp_path, "recording_stereo_225319", 1892.0, 373.0),
    )
    evidence = {
        str(unit.path / "stereo/stereo_000.mkv"): VideoEvidence(
            relative_path=f"{unit.facts.relative_path}/stereo/stereo_000.mkv",
            size_bytes=100,
            packet_count=300,
            pts_first_s=0.0,
            pts_last_s=9.967,
            duration_s=10.0,
            frame_rate=30.0,
            pts_monotonic=True,
            keyframes=1,
        )
        for unit in units
    }

    results = group_recordings(units, evidence)

    assert len(results) == 1
    assert results[0].unit_paths == tuple(unit.facts.relative_path for unit in units)
    assert len(results[0].segments) == 3


def test_standalone_continuations_do_not_cross_long_gaps_or_dates(tmp_path: Path) -> None:
    units = (
        _standalone_unit(tmp_path, "first", 1000.0, 100.0),
        _standalone_unit(tmp_path, "long_gap", 1500.0, 100.0),
        _standalone_unit(tmp_path, "next_day", 1600.0, 100.0),
    )
    units = (
        units[0],
        units[1],
        Unit(
            units[2].path,
            SessionFacts(
                relative_path="next_day",
                kind=UnitKind.FINAL,
                capture_date="2026-11-27",
                created_epoch=1600.0,
                standalone_stereo=True,
                sync_wall_s=100.0,
                sync_ok=True,
                has_stop_log=True,
            ),
        ),
    )

    results = group_recordings(units, {}, allow_missing_media=True)

    assert len(results) == 3
