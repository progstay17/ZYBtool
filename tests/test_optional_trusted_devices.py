"""Trusted-device pairing must remain optional for the normal pipeline."""

from pathlib import Path

from zybtool import settings
from zybtool.pipeline import _verify_qr_if_configured


def test_missing_allowlist_skips_qr_checks_without_blocking_pipeline(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        settings,
        "settings_status",
        lambda: {
            "decoder_key_configured": True,
            "allowlist_configured": False,
        },
    )

    def unexpected_key_load() -> bytes:
        raise AssertionError("decoder key must not be loaded without trusted devices")

    monkeypatch.setattr(settings, "load_decoder_private_key", unexpected_key_load)
    recordings = ()

    result = _verify_qr_if_configured(recordings, (), tmp_path)

    assert result is recordings
