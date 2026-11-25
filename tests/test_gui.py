"""Desktop UI import and smoke tests."""

from __future__ import annotations

from zybtool import gui


def test_gui_module_exposes_application_and_entrypoint() -> None:
    assert gui.ZYBToolApp is not None
    assert callable(gui.main)


def test_gui_self_test_uses_local_settings(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        gui,
        "settings_status",
        lambda: {
            "storage": "C:/ZYBTool-test",
            "decoder_key_configured": False,
        },
    )

    assert gui.main(["--self-test"]) == 0
    output = capsys.readouterr().out
    assert "Tkinter:" in output
    assert "Decoder key configured: False" in output
