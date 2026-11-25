from pathlib import Path

from zybtool import settings
from zybtool.models import RecordingResult, ResultStatus
from zybtool.pipeline import _verify_qr_if_configured


def test_qr_scan_is_not_skipped_when_private_key_is_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "settings_status", lambda: {"decoder_key_configured": False})

    def unexpected_key_load() -> bytes:
        raise AssertionError("private key must not be loaded when it is not configured")

    monkeypatch.setattr(settings, "load_decoder_private_key", unexpected_key_load)
    seen: list[bytes | None] = []

    def fake_verify(recording: RecordingResult, source_root: Path, *, private_key: bytes | None):
        seen.append(private_key)
        from zybtool.models import QRVerification

        return QRVerification(
            ResultStatus.QR_DECRYPT_FAILED,
            reasons=("QR MQ1 terdeteksi, tetapi private key decoder belum diimpor.",),
        )

    import zybtool.qrscan

    monkeypatch.setattr(zybtool.qrscan, "verify_recording_qr", fake_verify)
    recording = RecordingResult(
        recording_id="recording-one",
        unit_paths=("record",),
        device_id=None,
        created_epoch=None,
        segments=(),
        actual_duration_s=None,
        status=ResultStatus.METADATA_ONLY,
        trust_level=0,
    )
    result = _verify_qr_if_configured((recording,), (), tmp_path)
    assert seen == [None]
    assert result[0].qr is not None
    assert result[0].qr.status is ResultStatus.QR_DECRYPT_FAILED
