from pathlib import Path

import av
import numpy as np
from metaqr import (
    Allowlist,
    Device,
    ReplayLog,
    encode,
    generate_device_keypair,
    generate_keypair,
    verify,
)
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


def test_metaqr_mq2_verification_uses_the_official_library() -> None:
    decoder = generate_keypair()
    signer = generate_device_keypair()
    allowlist = Allowlist([Device("camera-phone-01", signer.public)])
    token = encode(_valid_payload(), decoder.public, signing_key=signer.private)
    result = verify(token, decoder.private, allowlist)
    assert result.device.id == "camera-phone-01"
    assert result.metadata == _valid_payload()


def _write_synthetic_video(
    path: Path, qr_image: np.ndarray, *, width: int = 400, height: int = 200
) -> None:
    container = av.open(str(path), mode="w")
    stream = container.add_stream("mpeg4", rate=10)
    stream.width = width
    stream.height = height
    stream.pix_fmt = "yuv420p"
    stream.codec_context.max_b_frames = 0

    for _ in range(12):
        image = np.full((height, width, 3), 255, dtype=np.uint8)
        y, x = 18, width - qr_image.shape[1] - 18
        image[y : y + qr_image.shape[0], x : x + qr_image.shape[1], :] = qr_image[:, :, None]
        frame = av.VideoFrame.from_ndarray(image, format="bgr24")
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def test_video_scanner_checks_eye_crops_and_finds_metaqr_token(tmp_path: Path) -> None:
    token = "MQ1:TEST-CAMERA-QR-TOKEN"
    qr_image = render(token, scale=5)
    video = tmp_path / "synthetic.mkv"
    meta = tmp_path / "meta.json"
    _write_synthetic_video(video, qr_image)
    meta.write_text(
        '{"usable":{"usable_start_s":0.0},"format":{"left_crop":[200,0,200,200],"right_crop":[0,0,200,200]}}',
        encoding="utf-8",
    )

    result = scan_video_tokens(video, meta, window_s=1.0, sample_fps=5.0, stop_after_votes=2)
    assert result.candidates
    assert result.candidates[0][0] == token
    assert result.candidates[0][1] >= 2


def test_unsigned_mq1_is_not_accepted_as_identity() -> None:
    decoder = generate_keypair()
    token = encode(_valid_payload(), decoder.public)
    assert token.startswith("MQ1:")
    assert not token.startswith("MQ2:")


def test_signed_qr_video_verification_and_cross_recording_replay(tmp_path: Path) -> None:
    decoder = generate_keypair()
    signer = generate_device_keypair()
    allowlist = Allowlist([Device("camera-phone-01", signer.public)])
    token = encode(_valid_payload(), decoder.public, signing_key=signer.private)
    qr_image = render(token, scale=2)

    video_path = tmp_path / "record" / "stereo" / "segment.mkv"
    meta_path = video_path.parent / "meta.json"
    video_path.parent.mkdir(parents=True)
    _write_synthetic_video(video_path, qr_image, width=900, height=450)
    meta_path.write_text(
        '{"usable":{"usable_start_s":0.0},"format":{"left_crop":[450,0,450,450],"right_crop":[0,0,450,450]}}',
        encoding="utf-8",
    )

    scanned = scan_video_tokens(video_path, meta_path, window_s=1.0, sample_fps=5.0)
    assert scanned.candidates
    assert scanned.candidates[0][0] == token

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
    first_recording = RecordingResult(
        recording_id="recording-one",
        unit_paths=("record",),
        device_id="fixture-device-001",
        created_epoch=1_795_416_606.0,
        segments=(segment,),
        actual_duration_s=1.2,
        status=ResultStatus.METADATA_ONLY,
        trust_level=0,
    )
    second_recording = RecordingResult(
        recording_id="recording-two",
        unit_paths=("record",),
        device_id="fixture-device-001",
        created_epoch=1_795_416_706.0,
        segments=(segment,),
        actual_duration_s=1.2,
        status=ResultStatus.METADATA_ONLY,
        trust_level=0,
    )
    replay = ReplayLog(tmp_path / "replay.jsonl")

    first = verify_recording_qr(
        first_recording,
        tmp_path,
        private_key=decoder.private,
        allowlist=allowlist,
        replay_log=replay,
    )
    assert first.status is ResultStatus.VERIFIED_WITH_WARNING
    assert first.signer_device_id == "camera-phone-01"
    assert first.payload == _valid_payload()
    assert first.token_id

    second = verify_recording_qr(
        second_recording,
        tmp_path,
        private_key=decoder.private,
        allowlist=allowlist,
        replay_log=replay,
    )
    assert second.status is ResultStatus.REPLAY_DETECTED
