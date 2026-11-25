from __future__ import annotations

import json
from pathlib import Path

from zybtool.workspace import load_preferences, save_preferences


def test_workspace_preferences_persist_per_windows_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZYBTOOL_DATA_DIR", str(tmp_path / "profile"))
    values = {
        "source_root": str(tmp_path / "source"),
        "report_root": str(tmp_path / "reports"),
        "excel_root": str(tmp_path / "excel"),
        "organized_root": str(tmp_path / "organized"),
    }
    save_preferences(values)
    loaded = load_preferences()
    assert loaded == {key: str(Path(value).resolve()) for key, value in values.items()}
    document = json.loads((tmp_path / "profile" / "preferences.json").read_text(encoding="utf-8"))
    assert set(document) == {"source_root", "report_root", "excel_root", "organized_root"}
