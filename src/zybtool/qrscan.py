"""Camera-aware scanning and encrypted-only MQ1 decryption for recording segments."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import av
import metaqr
from metaqr.errors import MetaQRError
from metaqr.qr import find_token

from zybtool.models import QRVerification, RecordingResult, ResultStatus


@dataclass(frozen=True, slots=True)
class QRScanResult:
    candidates: tuple[tuple[str, int], ...]
    frames_scanned: int
    first_seen_s: dict[str, float]


def _read_crop_rectangles(
    meta_path: Path, frame_width: int, frame_height: int
) -> tuple[tuple[str, tuple[int, int, int, int]], ...]:
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ()
    if not isinstance(meta, dict):
        return ()
    fmt = meta.get("format")
    if not isinstance(fmt, dict):
        return ()
    crops: list[tuple[str, tuple[int, int, int, int]]] = []
    for field, label in (("left_crop", "left-eye"), ("right_crop", "right-eye")):
        value = fmt.get(field)
        if (
            isinstance(value, list)
            and len(value) == 4
            and all(isinstance(item, int) and not isinstance(item, bool) for item in value)
        ):
            x, y, width, height = value
            if x >= 0 and y >= 0 and width > 0 and height > 0:
                x2, y2 = min(x + width, frame_width), min(y + height, frame_height)
                if x < x2 and y < y2:
                    crops.append((label, (x, y, x2, y2)))
    return tuple(crops) or (("full-frame-fallback", (0, 0, frame_width, frame_height)),)


def scan_video_tokens(
    video_path: Path | str,
    meta_path: Path | str,
    *,
    start_s: float | None = None,
    window_s: float = 30.0,
    sample_fps: float = 5.0,
    stop_after_votes: int = 3,
) -> QRScanResult:
    """Sample video frames with PyAV, searching the two configured eye crops only."""
    if window_s <= 0 or sample_fps <= 0 or stop_after_votes < 0:
        raise ValueError(
            "window_s/sample_fps harus positif dan stop_after_votes tidak boleh negatif"
        )
    path = Path(video_path)
    sidecar = Path(meta_path)
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"meta.json tidak dapat dibaca ({type(exc).__name__})") from None
    if not isinstance(meta, dict):
        raise RuntimeError("meta.json bukan object")
    usable = meta.get("usable")
    if start_s is None and isinstance(usable, dict):
        candidate = usable.get("usable_start_s")
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
            start_s = float(candidate)
    start = max(0.0, start_s or 0.0)
    stop = start + window_s
    votes: Counter[str] = Counter()
    first_seen: dict[str, float] = {}
    scanned = 0
    next_sample = start
    try:
        with av.open(str(path), mode="r") as container:
            stream = next((item for item in container.streams if item.type == "video"), None)
            if stream is None:
                raise RuntimeError("Video stream tidak ditemukan")
            for frame in container.decode(stream):
                if not isinstance(frame, av.VideoFrame):
                    continue
                if frame.pts is None or frame.time_base is None:
                    continue
                timestamp = float(frame.pts * frame.time_base)
                if timestamp < start:
                    continue
                if timestamp > stop:
                    break
                if timestamp + 1e-6 < next_sample:
                    continue
                next_sample += 1.0 / sample_fps
                image = frame.to_ndarray(format="bgr24")
                height, width = image.shape[:2]
                rectangles = _read_crop_rectangles(sidecar, width, height)
                found: set[str] = set()
                for _label, (x1, y1, x2, y2) in rectangles:
                    token = find_token(image[y1:y2, x1:x2])
                    if token:
                        found.add(token)
                scanned += 1
                for token in found:
                    votes[token] += 1
                    first_seen.setdefault(token, timestamp)
                    if stop_after_votes and votes[token] >= stop_after_votes:
                        break
                if stop_after_votes and any(count >= stop_after_votes for count in votes.values()):
                    break
    except (OSError, av.error.FFmpegError) as exc:
        raise RuntimeError(f"Gagal membaca video QR ({type(exc).__name__})") from None
    return QRScanResult(tuple(votes.most_common()), scanned, first_seen)


def validate_zyb_payload(payload: dict[str, Any]) -> tuple[bool, tuple[str, ...]]:
    """Accept AITQR's account-configured payload; do not impose a fixed field schema."""
    if not isinstance(payload, dict):
        return False, ("Isi QR harus berupa JSON object.",)
    if not payload:
        return False, ("Payload JSON kosong.",)
    return True, ()


def verify_recording_qr(
    recording: RecordingResult,
    source_root: Path | str,
    *,
    private_key: bytes | None = None,
) -> QRVerification:
    """Decrypt MQ1 tokens; payload fields are defined by the selected AITQR account profile."""
    root = Path(source_root)
    best_error: QRVerification | None = None
    for segment in recording.segments:
        video_path = root / Path(segment.video.relative_path)
        meta_path = root / Path(segment.unit_path) / Path(segment.camera) / "meta.json"
        try:
            scan = scan_video_tokens(video_path, meta_path)
        except (OSError, RuntimeError, ValueError) as exc:
            best_error = QRVerification(
                ResultStatus.QR_MISSING,
                source_video=segment.video.relative_path,
                reasons=(f"QR scan gagal: {exc}",),
            )
            continue
        candidates = sorted(scan.candidates, key=lambda pair: scan.first_seen_s.get(pair[0], 0.0))
        for token, votes in candidates:
            try:
                version = metaqr.token_version(token)
            except MetaQRError as exc:
                best_error = QRVerification(
                    ResultStatus.QR_DECRYPT_FAILED,
                    source_video=segment.video.relative_path,
                    votes=votes,
                    reasons=(str(exc),),
                )
                continue
            if version != 1:
                best_error = QRVerification(
                    ResultStatus.QR_DECRYPT_FAILED,
                    token_version=version,
                    source_video=segment.video.relative_path,
                    time_s=scan.first_seen_s.get(token),
                    votes=votes,
                    reasons=(
                        "Token MQ2 lama tidak didukung. AITQR harus menerbitkan QR terenkripsi MQ1.",
                    ),
                )
                continue
            if private_key is None:
                return QRVerification(
                    ResultStatus.QR_DECRYPT_FAILED,
                    token_version=1,
                    source_video=segment.video.relative_path,
                    time_s=scan.first_seen_s.get(token),
                    votes=votes,
                    reasons=("QR MQ1 terdeteksi, tetapi private key decoder belum diimpor.",),
                )
            try:
                payload = metaqr.decode(token, private_key)
            except MetaQRError as exc:
                best_error = QRVerification(
                    ResultStatus.QR_DECRYPT_FAILED,
                    token_version=1,
                    source_video=segment.video.relative_path,
                    time_s=scan.first_seen_s.get(token),
                    votes=votes,
                    reasons=(f"Dekripsi QR gagal: {type(exc).__name__}: {exc}",),
                )
                continue
            if not isinstance(payload, dict) or not payload:
                best_error = QRVerification(
                    ResultStatus.METADATA_MISMATCH,
                    token_version=1,
                    payload=payload if isinstance(payload, dict) else None,
                    source_video=segment.video.relative_path,
                    time_s=scan.first_seen_s.get(token),
                    votes=votes,
                    reasons=("Payload QR bukan JSON object yang berisi data.",),
                )
                continue
            device_id = payload.get("di")
            if (
                recording.device_id
                and isinstance(device_id, str)
                and device_id != recording.device_id
            ):
                best_error = QRVerification(
                    ResultStatus.METADATA_MISMATCH,
                    token_version=1,
                    payload=payload,
                    source_video=segment.video.relative_path,
                    time_s=scan.first_seen_s.get(token),
                    votes=votes,
                    reasons=(
                        f"Payload device ID {device_id!r} tidak cocok dengan session {recording.device_id!r}",
                    ),
                )
                continue
            token_id = hashlib.sha256(token.encode("ascii")).hexdigest()[:16]
            return QRVerification(
                ResultStatus.QR_DECRYPTED,
                token_version=1,
                token_id=token_id,
                payload=payload,
                source_video=segment.video.relative_path,
                time_s=scan.first_seen_s.get(token),
                votes=votes,
                reasons=(
                    "QR terenkripsi MQ1 berhasil didekripsi; identitas pengirim tidak diverifikasi.",
                ),
            )
    return best_error or QRVerification(
        ResultStatus.QR_MISSING,
        reasons=("Tidak ada QR terenkripsi Metaqr yang ditemukan pada jendela pemindaian.",),
    )


def verify_with_saved_settings(
    recording: RecordingResult, source_root: Path | str
) -> QRVerification:
    """Convenience entry point using this Windows user's protected decoder key."""
    from zybtool.settings import load_decoder_private_key

    return verify_recording_qr(recording, source_root, private_key=load_decoder_private_key())
