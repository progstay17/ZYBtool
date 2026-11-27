import json
from dataclasses import replace
from pathlib import Path

import av
import cv2
import metaqr
import numpy as np
from metaqr.qr import render

from zybtool.models import RecordingResult, ResultStatus, Segment, VideoEvidence
from zybtool.qrscan import (
    QRScanResult,
    scan_video_tokens,
    validate_zyb_payload,
    verify_recording_qr,
)


def _valid_payload(device_id: str = "fixture-device-001") -> dict[str, object]:
    return {
        "p": "zyb-recording",
        "pv": 1,
        "s": "0123456789ABCDEF",
        "r": "BLACK",
        "dn": "ZY010",
        "di": device_id,
        "l": "SITE01",
        "a": "Activity",
        "sh": 1,
        "b": "MM01",
    }


def test_payload_contract_validation_accepts_account_configured_fields() -> None:
    ok, reasons = validate_zyb_payload(_valid_payload())
    assert ok and not reasons

    payload = _valid_payload()
    payload["operator"] = "Fadhil"
    payload["site_code"] = "SITE01"
    payload["custom_profile_flag"] = False
    ok, reasons = validate_zyb_payload(payload)
    assert ok and not reasons

    ok, reasons = validate_zyb_payload({})
    assert not ok
    assert "profile" in reasons[0].lower()

    invalid_version = _valid_payload()
    invalid_version["pv"] = 2
    ok, reasons = validate_zyb_payload(invalid_version)
    assert not ok
    assert "pv=1" in reasons[0]

    invalid_session = _valid_payload()
    invalid_session["s"] = "not-a-valid-session"
    ok, reasons = validate_zyb_payload(invalid_session)
    assert not ok
    assert "session id" in reasons[0].lower()

    custom_profile_payload = {
        "p": "zyb-recording",
        "pv": 1,
        "s": "3F30WDDZWKDYPZJD",
        "c": "testing",
        "d": "ZY007",
        "l": "MM3201",
        "m": "test only",
        "ss": "5",
        "t": "Kitchen",
    }
    ok, reasons = validate_zyb_payload(custom_profile_payload)
    assert ok and not reasons


def test_metaqr_mq1_is_encrypted_and_needs_only_decoder_private_key() -> None:
    decoder = metaqr.generate_keypair()
    token = metaqr.encode(_valid_payload(), decoder.public)
    assert metaqr.token_version(token) == 1
    assert token.startswith("MQ1:")
    assert metaqr.decode(token, decoder.private) == _valid_payload()


def _write_synthetic_video(
    path: Path,
    qr_image: np.ndarray,
    *,
    width: int = 400,
    height: int = 200,
    frame_count: int = 12,
) -> None:
    container = av.open(str(path), mode="w")
    stream = container.add_stream("mpeg4", rate=10)
    stream.width = width
    stream.height = height
    stream.pix_fmt = "yuv420p"
    eye = cv2.resize(qr_image, (width // 2, height), interpolation=cv2.INTER_NEAREST)
    if eye.ndim == 2:
        eye = np.repeat(eye[:, :, None], 3, axis=2)
    for _ in range(frame_count):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, : width // 2] = eye
        frame[:, width // 2 :] = eye
        video_frame = av.VideoFrame.from_ndarray(frame, format="rgb24")
        for packet in stream.encode(video_frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def _recording(video_path: Path) -> RecordingResult:
    video = VideoEvidence(
        relative_path="record/stereo/segment.mkv",
        size_bytes=video_path.stat().st_size,
        packet_count=12,
        pts_first_s=0.0,
        pts_last_s=1.1,
        duration_s=1.2,
        frame_rate=10.0,
        pts_monotonic=True,
        keyframes=1,
    )
    segment = Segment("record", "stereo", video)
    return RecordingResult(
        recording_id="recording-one",
        unit_paths=("record",),
        device_id="fixture-device-001",
        created_epoch=1_795_416_606.0,
        segments=(segment,),
        actual_duration_s=1.2,
        status=ResultStatus.METADATA_ONLY,
        trust_level=0,
    )


def _video_with_token(tmp_path: Path, payload: dict[str, object] | None = None) -> tuple[Path, str]:
    decoder = metaqr.generate_keypair()
    token = metaqr.encode(payload if payload is not None else _valid_payload(), decoder.public)
    qr_image = render(token, scale=2)
    video_path = tmp_path / "record" / "stereo" / "segment.mkv"
    meta_path = video_path.parent / "meta.json"
    video_path.parent.mkdir(parents=True)
    _write_synthetic_video(video_path, qr_image, width=900, height=450)
    meta_path.write_text(
        '{"usable":{"usable_start_s":0.0},"format":{"left_crop":[450,0,450,450],"right_crop":[0,0,450,450]}}',
        encoding="utf-8",
    )
    return video_path, decoder.private.hex()


def test_qr_verification_does_not_scan_later_segments(tmp_path: Path, monkeypatch) -> None:
    video_path = tmp_path / "record" / "stereo" / "segment.mkv"
    recording = _recording(video_path)
    second_video = VideoEvidence(
        relative_path="record/stereo/segment_000002.mkv",
        size_bytes=100,
        packet_count=10,
        pts_first_s=0.0,
        pts_last_s=0.9,
        duration_s=1.0,
        frame_rate=10.0,
        pts_monotonic=True,
        keyframes=1,
    )
    recording = replace(
        recording,
        segments=(*recording.segments, Segment("record", "stereo", second_video)),
    )
    calls: list[str] = []

    def fake_scan(path: Path, meta_path: Path, **kwargs: object) -> QRScanResult:
        calls.append(str(path))
        return QRScanResult((), 0, {})

    import zybtool.qrscan as qrscan_module

    monkeypatch.setattr(qrscan_module, "scan_video_tokens", fake_scan)
    result = verify_recording_qr(recording, tmp_path, private_key=None)

    assert result.status is ResultStatus.QR_MISSING
    assert calls == [str(video_path)]


def test_default_qr_scan_is_limited_to_first_five_seconds(tmp_path: Path) -> None:
    video_path = tmp_path / "record" / "stereo" / "long-video.mkv"
    meta_path = video_path.parent / "meta.json"
    video_path.parent.mkdir(parents=True)
    _write_synthetic_video(
        video_path,
        np.zeros((100, 100), dtype=np.uint8),
        width=200,
        height=100,
        frame_count=100,
    )
    meta_path.write_text('{"usable":{"usable_start_s":0.0}}', encoding="utf-8")

    scanned = scan_video_tokens(video_path, meta_path)

    assert scanned.frames_scanned == 25


def test_mq1_video_scan_decrypts_payload_without_allowlist(tmp_path: Path) -> None:
    video_path, private_hex = _video_with_token(tmp_path)
    decoder_private = bytes.fromhex(private_hex)
    recording = _recording(video_path)
    scanned = scan_video_tokens(
        video_path, video_path.parent / "meta.json", window_s=1.0, sample_fps=5.0
    )
    assert scanned.candidates and scanned.candidates[0][0].startswith("MQ1:")
    result = verify_recording_qr(recording, tmp_path, private_key=decoder_private)
    assert result.status is ResultStatus.QR_DECRYPTED
    assert result.signer_device_id is None
    assert result.payload == _valid_payload()
    assert result.token_id
    assert "Device ID QR cocok" in result.reasons[0]


def test_custom_account_payload_without_camera_id_is_decrypted_without_warning(
    tmp_path: Path,
) -> None:
    payload = {
        "p": "zyb-recording",
        "pv": 1,
        "s": "3F30WDDZWKDYPZJD",
        "c": "testing",
        "d": "ZY007",
        "l": "MM3201",
        "m": "test only",
        "ss": "5",
        "t": "Kitchen",
    }
    video_path, private_hex = _video_with_token(tmp_path, payload)
    result = verify_recording_qr(
        _recording(video_path), tmp_path, private_key=bytes.fromhex(private_hex)
    )
    assert result.status is ResultStatus.QR_DECRYPTED
    assert result.payload == payload
    assert "opsional" in result.reasons[0]


def test_camera_device_id_mismatch_is_rejected(tmp_path: Path) -> None:
    payload = _valid_payload(device_id="different-camera")
    video_path, private_hex = _video_with_token(tmp_path, payload)
    result = verify_recording_qr(
        _recording(video_path), tmp_path, private_key=bytes.fromhex(private_hex)
    )
    assert result.status is ResultStatus.METADATA_MISMATCH
    assert "tidak cocok" in result.reasons[0]


def test_qr_is_still_detected_when_private_key_is_not_imported(tmp_path: Path) -> None:
    video_path, _private_hex = _video_with_token(tmp_path)
    result = verify_recording_qr(_recording(video_path), tmp_path, private_key=None)
    assert result.status is ResultStatus.QR_DECRYPT_FAILED
    assert "private key decoder belum diimpor" in result.reasons[0]


def test_shared_aitqr_mq1_vector_decrypts_in_python(tmp_path: Path) -> None:
    vector_path = Path(__file__).parent / "fixtures" / "aitqr-mq1-vectors.json"
    vector = json.loads(vector_path.read_text(encoding="utf-8"))
    assert vector["test_only"] is True
    assert metaqr.token_version(vector["token"]) == 1
    assert (
        metaqr.decode(vector["token"], bytes.fromhex(vector["decoder_private_hex"]))
        == vector["payload"]
    )
