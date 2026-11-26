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


def test_decrypted_valid_qr_is_verified_with_sender_authentication_warning() -> None:
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
        reasons=("Envelope profil valid. MQ1 tidak mengautentikasi penerbit QR.",),
    )

    status, trust, reasons = evaluate_status(facts, segments, qr=qr)

    assert status is ResultStatus.VERIFIED_WITH_WARNING
    assert trust == 1
    assert any("tidak mengautentikasi" in reason.lower() for reason in reasons)
