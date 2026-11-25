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
