import json
from pathlib import Path

import av
import cv2
import metaqr
import numpy as np
from metaqr.qr import render

from zybtool.models import RecordingResult, ResultStatus, Segment, VideoEvidence
from zybtool.qrscan import scan_video_tokens, validate_zyb_payload, verify_recording_qr


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


def test_payload_contract_validation() -> None:
    ok, reasons = validate_zyb_payload(_valid_payload())
    assert ok and not reasons
    payload = _valid_payload()
    payload["unexpected"] = "not allowed"
    ok, reasons = validate_zyb_payload(payload)
    assert not ok
    assert "Field payload" in reasons[0]


def test_metaqr_mq1_is_encrypted_and_needs_only_decoder_private_key() -> None:
    decoder = metaqr.generate_keypair()
    token = metaqr.encode(_valid_payload(), decoder.public)
    assert metaqr.token_version(token) == 1
    assert token.startswith("MQ1:")
    assert metaqr.decode(token, decoder.private) == _valid_payload()


def _write_synthetic_video(
    path: Path, qr_image: np.ndarray, *, width: int = 400, height: int = 200
) -> None:
    container = av.open(str(path), mode="w")
    stream = container.add_stream("mpeg4", rate=10)
    stream.width = width
    stream.height = height
    stream.pix_fmt = "yuv420p"
    eye = cv2.resize(qr_image, (width // 2, height), interpolation=cv2.INTER_NEAREST)
    if eye.ndim == 2:
        eye = np.repeat(eye[:, :, None], 3, axis=2)
    for _ in range(12):
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


def _video_with_token(tmp_path: Path) -> tuple[Path, str]:
    decoder = metaqr.generate_keypair()
    token = metaqr.encode(_valid_payload(), decoder.public)
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
