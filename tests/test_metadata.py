from pathlib import Path

from zybtool.discovery import discover_units

FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_sample1_facts_are_parsed_without_using_people_fields() -> None:
    units = {item.facts.relative_path: item for item in discover_units(FIXTURES)}
    facts = units["sample1_flat"].facts

    assert facts.device_id == "fixture-device-001"
    assert facts.object_id == "fixture-object-001"
    assert facts.live_root == ".live_20250115_145003"
    assert facts.claimed_video_duration_s == 509.166
    assert facts.sync_ok is True
    assert facts.has_stop_log is True
    assert facts.log_stop_durations_s == (510.1,)
    assert facts.restart_count == 0


def test_csv_parser_uses_mono_us_and_detects_order() -> None:
    units = {item.facts.relative_path: item for item in discover_units(FIXTURES)}
    timeline = units["sample1_flat"].facts.csv_timelines[0]

    assert timeline.rows == 8
    assert timeline.monotonic is True
    assert timeline.duration_s is not None
    assert 507.4 < timeline.duration_s < 507.5


def test_live_without_stop_is_preserved_as_incomplete_evidence() -> None:
    units = {item.facts.relative_path: item for item in discover_units(FIXTURES)}
    facts = units["sample2_live/.live_20250210_174436"].facts

    assert facts.has_stop_log is False
    assert facts.restart_count == 2
    assert "session_sync.json" in facts.missing_files
    assert "t0.json" in facts.missing_files
