from pathlib import Path

from zybtool.discovery import discover_units
from zybtool.grouper import group_recordings
from zybtool.models import ResultStatus

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
