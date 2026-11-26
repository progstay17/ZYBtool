from __future__ import annotations

from zybtool.models import (
    QRVerification,
    ResultStatus,
    Segment,
    SessionFacts,
    UnitKind,
    VideoEvidence,
)
from zybtool.status import evaluate_status


def test_decrypted_valid_qr_is_verified_without_sender_authentication_requirement() -> None:
    facts = (
        SessionFacts(
            relative_path="recording",
            kind=UnitKind.FINAL,
            has_stop_log=True,
            sync_ok=True,
        ),
    )
    video = VideoEvidence(
        relative_path="recording/stereo/segment.mkv",
        size_bytes=100,
        packet_count=30,
        pts_first_s=0.0,
        pts_last_s=0.967,
        duration_s=1.0,
        frame_rate=30.0,
        pts_monotonic=True,
        keyframes=1,
    )
    segments = (Segment("recording", "stereo", video),)
    qr = QRVerification(
        status=ResultStatus.QR_DECRYPTED,
        payload={
            "p": "zyb-recording",
            "pv": 1,
            "s": "3F30WDDZWKDYPZJD",
            "c": "testing",
            "d": "ZY007",
            "l": "MM3201",
            "ss": "5",
            "t": "Kitchen",
        },
        reasons=("Envelope profil valid dan berhasil didekripsi.",),
    )

    status, trust, reasons = evaluate_status(facts, segments, qr=qr)

    assert status is ResultStatus.VERIFIED
    assert trust == 3
    assert any("berhasil didekripsi" in reason.lower() for reason in reasons)
    assert not any("warning" in reason.lower() for reason in reasons)


def test_standalone_sync_gate_failures_are_warnings_when_qr_and_media_pass() -> None:
    facts = (
        SessionFacts(
            relative_path="recording_stereo",
            kind=UnitKind.FINAL,
            standalone_stereo=True,
            has_stop_log=True,
            sync_ok=False,
            sync_fails=("wall_skew=4.34s",),
        ),
    )
    video = VideoEvidence(
        relative_path="recording_stereo/stereo/stereo_000.mkv",
        size_bytes=100,
        packet_count=30,
        pts_first_s=0.0,
        pts_last_s=0.967,
        duration_s=1.0,
        frame_rate=30.0,
        pts_monotonic=True,
        keyframes=1,
    )
    qr = QRVerification(
        status=ResultStatus.QR_DECRYPTED,
        payload={"p": "zyb-recording", "pv": 1, "s": "3F30WDDZWKDYPZJD"},
    )

    status, trust, reasons = evaluate_status(
        facts, (Segment("recording_stereo", "stereo", video),), qr=qr
    )

    assert status is ResultStatus.VERIFIED_WITH_WARNING
    assert trust == 2
    assert any("wall_skew=4.34s" in reason for reason in reasons)


def test_standalone_sync_failure_downgrades_to_warning_not_incomplete() -> None:
    facts = (
        SessionFacts(
            relative_path="recording_stereo",
            kind=UnitKind.FINAL,
            standalone_stereo=True,
            has_stop_log=True,
            sync_ok=False,
            sync_fails=("wall_skew=7.77s",),
            sync_wall_s=8.77,
            log_stop_durations_s=(8.77,),
        ),
    )
    video = VideoEvidence(
        relative_path="recording_stereo/stereo/stereo_000.mkv",
        size_bytes=100,
        packet_count=30,
        pts_first_s=0.0,
        pts_last_s=0.967,
        duration_s=1.0,
        frame_rate=30.0,
        pts_monotonic=True,
        keyframes=1,
    )
    qr = QRVerification(
        status=ResultStatus.QR_DECRYPTED,
        payload={"p": "zyb-recording", "pv": 1, "s": "3F30WDDZWKDYPZJD"},
    )

    status, trust, reasons = evaluate_status(
        facts, (Segment("recording_stereo", "stereo", video),), qr=qr
    )

    assert status is ResultStatus.VERIFIED_WITH_WARNING
    assert trust == 2
    assert any("wall_skew=7.77s" in reason for reason in reasons)


def test_standalone_sync_duration_has_three_second_capture_tolerance() -> None:
    facts = (
        SessionFacts(
            relative_path="recording_stereo",
            kind=UnitKind.FINAL,
            standalone_stereo=True,
            has_stop_log=True,
            sync_ok=True,
            sync_wall_s=3.5,
        ),
    )
    video = VideoEvidence(
        relative_path="recording_stereo/stereo/stereo_000.mkv",
        size_bytes=100,
        packet_count=30,
        pts_first_s=0.0,
        pts_last_s=0.967,
        duration_s=1.0,
        frame_rate=30.0,
        pts_monotonic=True,
        keyframes=1,
    )
    qr = QRVerification(
        status=ResultStatus.QR_DECRYPTED,
        payload={"p": "zyb-recording", "pv": 1, "s": "3F30WDDZWKDYPZJD"},
    )

    status, trust, _ = evaluate_status(
        facts, (Segment("recording_stereo", "stereo", video),), qr=qr
    )

    assert status is ResultStatus.VERIFIED
    assert trust == 3
