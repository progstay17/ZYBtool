"""Camera-aware Metaqr scanning and strict MQ2 verification for recording segments."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import av
import metaqr
from metaqr.errors import (
    DecryptError,
    InvalidSignatureError,
    MetaQRError,
    ReplayDetectedError,
    RevokedDeviceError,
    UnknownDeviceError,
    UnsignedTokenError,
)
from metaqr.qr import find_token

from zybtool.models import QRVerification, RecordingResult, ResultStatus
from zybtool.settings import load_allowlist, load_decoder_private_key


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
    # Unknown layouts are not guessed: use the full frame as a documented fallback.
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
    """Validate the current consumer-owned zyb-recording/v1 contract."""
    expected = {"p", "pv", "s", "r", "dn", "di", "l", "a", "sh", "b"}
    problems: list[str] = []
    if set(payload) != expected:
        problems.append("Field payload tidak sama dengan zyb-recording/v1")
        return False, tuple(problems)
    if payload.get("p") != "zyb-recording" or payload.get("pv") != 1:
        problems.append("Penanda payload bukan zyb-recording/v1")
    if not isinstance(payload.get("s"), str) or not re.fullmatch(
        r"[0-9A-HJKMNP-TV-Z]{16}", payload["s"]
    ):
        problems.append("Session ID tidak sesuai format")
    if not isinstance(payload.get("r"), str) or not 1 <= len(payload["r"]) <= 40:
        problems.append("Recorder tidak valid")
    if not isinstance(payload.get("dn"), str) or not re.fullmatch(r"ZY[0-9]{3,4}", payload["dn"]):
        problems.append("Device number tidak valid")
    for field in ("di", "l", "a"):
        value = payload.get(field)
        if not isinstance(value, str) or not 1 <= len(value) <= 80:
            problems.append(f"Field {field} tidak valid")
    if (
        isinstance(payload.get("sh"), bool)
        or not isinstance(payload.get("sh"), int)
        or not 1 <= payload["sh"] <= 3
    ):
        problems.append("Shift tidak valid")
    if not isinstance(payload.get("b"), str) or not re.fullmatch(r"MM[0-9]{2,4}", payload["b"]):
        problems.append("Batch tidak valid")
    return not problems, tuple(problems)


def verify_recording_qr(
    recording: RecordingResult,
    source_root: Path | str,
    *,
    private_key: bytes | None = None,
    allowlist: Any | None = None,
    replay_log: Any | None = None,
) -> QRVerification:
    """Find and verify signed QR tokens; unsigned MQ1 is never accepted as trusted identity."""
    if private_key is None:
        private_key = load_decoder_private_key()
    if allowlist is None:
        allowlist = load_allowlist()
    root = Path(source_root)
    best_error: QRVerification | None = None
    replay = replay_log
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
                verified = metaqr.verify(token, private_key, allowlist)
            except ReplayDetectedError as exc:
                best_error = QRVerification(
                    ResultStatus.REPLAY_DETECTED,
                    2,
                    source_video=segment.video.relative_path,
                    time_s=scan.first_seen_s.get(token),
                    votes=votes,
                    reasons=(str(exc),),
                )
                continue
            except UnknownDeviceError as exc:
                best_error = QRVerification(
                    ResultStatus.UNKNOWN_DEVICE,
                    2,
                    source_video=segment.video.relative_path,
                    time_s=scan.first_seen_s.get(token),
                    votes=votes,
                    reasons=(str(exc),),
                )
                continue
            except (
                InvalidSignatureError,
                RevokedDeviceError,
                UnsignedTokenError,
                DecryptError,
                MetaQRError,
            ) as exc:
                best_error = QRVerification(
                    ResultStatus.INVALID_SIGNATURE,
                    2,
                    source_video=segment.video.relative_path,
                    time_s=scan.first_seen_s.get(token),
                    votes=votes,
                    reasons=(f"Token ditolak Metaqr: {type(exc).__name__}: {exc}",),
                )
                continue
            valid, problems = validate_zyb_payload(verified.metadata)
            if not valid:
                best_error = QRVerification(
                    ResultStatus.METADATA_MISMATCH,
                    2,
                    signer_device_id=verified.device.id,
                    payload=verified.metadata,
                    source_video=segment.video.relative_path,
                    time_s=scan.first_seen_s.get(token),
                    votes=votes,
                    reasons=problems,
                )
                continue
            if recording.device_id and verified.metadata["di"] != recording.device_id:
                best_error = QRVerification(
                    ResultStatus.METADATA_MISMATCH,
                    2,
                    signer_device_id=verified.device.id,
                    payload=verified.metadata,
                    source_video=segment.video.relative_path,
                    time_s=scan.first_seen_s.get(token),
                    votes=votes,
                    reasons=(
                        f"Payload device ID {verified.metadata['di']!r} tidak cocok dengan session {recording.device_id!r}",
                    ),
                )
                continue
            if replay is not None:
                try:
                    replay.check_and_record(
                        verified.token_id, recording.recording_id, verified.device.id
                    )
                except ReplayDetectedError as exc:
                    best_error = QRVerification(
                        ResultStatus.REPLAY_DETECTED,
                        2,
                        token_id=verified.token_id,
                        signer_device_id=verified.device.id,
                        payload=verified.metadata,
                        source_video=segment.video.relative_path,
                        time_s=scan.first_seen_s.get(token),
                        votes=votes,
                        reasons=(str(exc),),
                    )
                    continue
            warnings = [
                "Signature MQ2 dan allow-list valid; korelasi waktu/session lengkap masih menunggu kontrak final AITQR."
            ]
            if verified.retired:
                warnings.append("Kunci penanda tangan berstatus retired.")
            return QRVerification(
                ResultStatus.VERIFIED_WITH_WARNING,
                2,
                verified.token_id,
                verified.device.id,
                verified.metadata,
                segment.video.relative_path,
                scan.first_seen_s.get(token),
                votes,
                verified.retired,
                tuple(warnings),
            )
    return best_error or QRVerification(
        ResultStatus.QR_MISSING,
        reasons=("Tidak ada QR Metaqr valid yang ditemukan pada jendela pemindaian.",),
    )


def verify_with_saved_settings(
    recording: RecordingResult, source_root: Path | str
) -> QRVerification:
    """Convenience entry point using this Windows user's protected settings."""
    from metaqr import ReplayLog

    from zybtool.settings import data_dir

    return verify_recording_qr(
        recording,
        source_root,
        replay_log=ReplayLog(data_dir() / "replay.jsonl"),
    )
