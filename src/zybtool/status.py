"""Single decision point for recording trust status and rejection reasons."""

from __future__ import annotations

from zybtool.models import QRVerification, ResultStatus, Segment, SessionFacts, UnitKind

CLAIM_TOLERANCE_S = 2.0
CSV_CROSS_TOLERANCE_S = 3.0


def evaluate_status(
    facts: tuple[SessionFacts, ...],
    segments: tuple[Segment, ...],
    *,
    ambiguous: bool = False,
    allow_missing_media: bool = False,
    qr: QRVerification | None = None,
) -> tuple[ResultStatus, int, tuple[str, ...]]:
    if ambiguous:
        return ResultStatus.AMBIGUOUS, 0, ("Bukti kandidat pengelompokan saling bertentangan",)

    reasons: list[str] = []
    if not facts:
        return ResultStatus.INCOMPLETE, 0, ("Tidak ada metadata unit",)

    for item in facts:
        if item.kind is not UnitKind.FINAL:
            reasons.append(f"{item.relative_path}: unit {item.kind.value} belum final")
        required_missing = [
            name for name in item.missing_files if not (allow_missing_media and name == "video MKV")
        ]
        if required_missing:
            reasons.append(
                f"{item.relative_path}: file wajib hilang: {', '.join(required_missing)}"
            )
        if not item.has_stop_log:
            reasons.append(f"{item.relative_path}: app.log tidak memiliki baris stop")
        if item.sync_ok is False or item.sync_fails:
            reasons.append(f"{item.relative_path}: session_sync gagal atau memiliki fails")
        for warning in item.warnings:
            reasons.append(f"{item.relative_path}: {warning}")

    if reasons:
        return ResultStatus.INCOMPLETE, 0, tuple(reasons)

    if not segments:
        if allow_missing_media:
            return (
                ResultStatus.METADATA_ONLY,
                0,
                ("Fixture tidak menyertakan file MKV; timeline belum diuji",),
            )
        return ResultStatus.INCOMPLETE, 0, ("Tidak ada file MKV untuk diperiksa",)

    for segment in segments:
        if segment.video.error:
            return (
                ResultStatus.CORRUPTED,
                0,
                (f"{segment.video.relative_path}: {segment.video.error}",),
            )
        if segment.video.duration_s is None or not segment.video.pts_monotonic:
            return (
                ResultStatus.CORRUPTED,
                0,
                (f"{segment.video.relative_path}: timeline video tidak dapat dipercaya",),
            )

    for item in facts:
        by_camera: dict[str, float] = {}
        for segment in segments:
            if segment.unit_path == item.relative_path and segment.video.duration_s is not None:
                by_camera[segment.camera] = (
                    by_camera.get(segment.camera, 0.0) + segment.video.duration_s
                )
        if not by_camera:
            continue
        actual = max(by_camera.values())
        claims: list[tuple[str, float]] = []
        if item.claimed_video_duration_s is not None:
            claims.append(("video_duration_s", item.claimed_video_duration_s))
        if item.segment_start_wall is not None and item.segment_stop_wall is not None:
            claims.append(("segment_start/stop", item.segment_stop_wall - item.segment_start_wall))
        if item.sync_wall_s is not None:
            claims.append(("session_sync", item.sync_wall_s))
        claims.extend(
            (f"app.log stop #{index + 1}", duration)
            for index, duration in enumerate(item.log_stop_durations_s)
        )
        for name, claimed in claims:
            if abs(claimed - actual) > CLAIM_TOLERANCE_S:
                return (
                    ResultStatus.METADATA_MISMATCH,
                    0,
                    (
                        f"{item.relative_path}: {name} berbeda {abs(claimed - actual):.3f} s dari timeline video",
                    ),
                )
        csv_values = [
            csv.duration_s
            for csv in item.csv_timelines
            if csv.duration_s is not None and csv.monotonic and not csv.error
        ]
        for value in csv_values:
            if abs(value - actual) > CSV_CROSS_TOLERANCE_S:
                return (
                    ResultStatus.METADATA_MISMATCH,
                    0,
                    (
                        f"{item.relative_path}: rentang mono_us berbeda {abs(value - actual):.3f} s dari timeline video",
                    ),
                )

    # The recording passed local structure/timeline checks and its AITQR envelope
    # was validated. MQ1 still cannot authenticate who issued the QR, so do not
    # claim an unqualified VERIFIED result.
    if qr is not None:
        if qr.status is ResultStatus.QR_DECRYPTED:
            return (
                ResultStatus.VERIFIED_WITH_WARNING,
                1,
                qr.reasons
                + ("Struktur metadata dan konsistensi timeline recording lolos pemeriksaan.",),
            )
        return qr.status, 0, qr.reasons or ("QR tidak dapat didekripsi atau dikorelasikan.",)

    return ResultStatus.METADATA_ONLY, 0, ("QR terenkripsi belum ditemukan.",)
