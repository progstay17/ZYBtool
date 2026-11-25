from __future__ import annotations

import json
from pathlib import Path

from zybtool.naming import (
    DEFAULT_TEMPLATE,
    build_folder_name,
    preview_folder_name,
    scan_json_file,
    validate_template,
)


def _payload() -> dict[str, object]:
    return {"b": "MM12", "r": "Recorder A", "dn": "ZY123", "sh": 2, "a": "Kitchen"}


def test_scanner_detects_nested_fields_and_array_indexes(tmp_path: Path) -> None:
    source = tmp_path / "session.json"
    source.write_text(
        json.dumps({"people": {"name": "Recorder B"}, "devices": [{"id": "ZY123"}]}),
        encoding="utf-8",
    )

    fields = scan_json_file(source)

    paths = {item["path"] for item in fields}
    assert "people.name" in paths
    assert "devices[0].id" in paths


def test_default_template_preserves_zyb_operational_order() -> None:
    result = build_folder_name(_payload(), {}, "2026-11-25")

    assert result == "20261125_MM12_RecorderA_ZY123_S2_Kitchen"


def test_no_shift_omits_session_token_without_s0() -> None:
    result = build_folder_name(
        _payload(),
        {},
        "2026-11-25",
        {"template": DEFAULT_TEMPLATE, "no_shift": True},
    )

    assert result == "20261125_MM12_RecorderA_ZY123_Kitchen"
    assert "S0" not in result
    assert "__" not in result


def test_custom_json_mapping_and_template() -> None:
    session = {
        "capture_date": "2026-11-25",
        "site": {"code": "MM99"},
        "people": {"name": "Recorder B"},
    }
    config = {
        "template": "{DATE}-{LOCATION_CODE}-{PERSON_NAME}-{DEVICE_ID}-{SESSION}-{ACTIVITY}",
        "field_map": {
            "DATE": "capture_date",
            "LOCATION_CODE": "site.code",
            "PERSON_NAME": "people.name",
        },
    }

    assert build_folder_name(_payload(), session, "2026-11-25", config) == (
        "20261125-MM99-RecorderB-ZY123-S2-Kitchen"
    )


def test_zero_shift_value_is_never_rendered_as_s0() -> None:
    result = build_folder_name(
        _payload(),
        {"shift": 0},
        "2026-11-25",
        {"field_map": {"SESSION": "shift"}},
    )

    assert result == "20261125_MM12_RecorderA_ZY123_Kitchen"
    assert "S0" not in result


def test_preview_omits_shift_and_uses_sample_fields() -> None:
    sample = {
        "capture_date": "2026-11-25",
        "b": "MM12",
        "r": "Recorder A",
        "dn": "ZY123",
        "sh": 2,
        "a": "Kitchen",
    }

    result = preview_folder_name(sample, {"no_shift": True})

    assert result == "20261125_MM12_RecorderA_ZY123_Kitchen"


def test_template_rejects_path_separators() -> None:
    try:
        validate_template("{DATE}/../{PERSON_NAME}")
    except ValueError as exc:
        assert "Separator" in str(exc)
    else:
        raise AssertionError("Unsafe folder path template was accepted")
