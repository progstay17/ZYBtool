from pathlib import Path

from zybtool.discovery import discover_units
from zybtool.models import UnitKind

FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_discovers_flat_primary_and_hidden_live_units() -> None:
    units = discover_units(FIXTURES)
    paths = {item.facts.relative_path for item in units}

    assert "sample1_flat" in paths
    assert "sample2_primary/recording_primary_fixture-002_20250210_123913_01" in paths
    assert "sample2_live/.live_20250209_091607" in paths
    assert "sample2_live/.live_20250210_174436" in paths
    assert len(units) == 4


def test_final_and_live_classification() -> None:
    units = {item.facts.relative_path: item for item in discover_units(FIXTURES)}

    assert units["sample1_flat"].facts.kind is UnitKind.FINAL
    assert (
        units["sample2_primary/recording_primary_fixture-002_20250210_123913_01"].facts.kind
        is UnitKind.FINAL
    )
    assert units["sample2_live/.live_20250210_174436"].facts.kind is UnitKind.LIVE


def test_standalone_stereo_capture_without_t0_is_final(tmp_path: Path) -> None:
    import json

    recording = tmp_path / "recording_stereo_20261126_223827"
    stereo = recording / "stereo"
    stereo.mkdir(parents=True)
    (recording / "session.json").write_text(
        json.dumps(
            {
                "type": "stereo_standalone",
                "created": 1795703907.9,
                "created_iso": "2026-11-26T22:38:27",
            }
        ),
        encoding="utf-8",
    )
    (recording / "session_sync.json").write_text(
        json.dumps({"ok": True, "wall_s": 452.384, "fails": []}),
        encoding="utf-8",
    )
    (stereo / "meta.json").write_text(
        json.dumps({"stream": "stereo_rgb", "mode": "standalone"}),
        encoding="utf-8",
    )
    (stereo / "stereo_000.mkv").write_bytes(b"fixture")
    (stereo / "stereo_000_imu_frametimes.csv").write_text(
        "frame_idx,mono_us\n0,1000000\n1,2000000\n", encoding="utf-8"
    )
    (stereo / "app.log").write_text(
        "[22:38:28] start\n[22:46:00] stop reason=request dur=452.4s\n",
        encoding="utf-8",
    )

    units = discover_units(tmp_path)
    assert len(units) == 1
    facts = units[0].facts
    assert facts.kind is UnitKind.FINAL
    assert facts.standalone_stereo is True
    assert facts.missing_files == ()
    assert facts.capture_date == "2026-11-26"
    assert facts.sync_ok is True
    assert facts.has_stop_log is True
