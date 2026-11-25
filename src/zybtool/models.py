"""Immutable domain models used across the verification pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class UnitKind(StrEnum):
    FINAL = "FINAL"
    LIVE = "LIVE"
    PARTIAL = "PARTIAL"


class ResultStatus(StrEnum):
    VERIFIED = "VERIFIED"
    VERIFIED_WITH_WARNING = "VERIFIED_WITH_WARNING"
    METADATA_ONLY = "METADATA_ONLY"
    QR_MISSING = "QR_MISSING"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    UNKNOWN_DEVICE = "UNKNOWN_DEVICE"
    REPLAY_DETECTED = "REPLAY_DETECTED"
    METADATA_MISMATCH = "METADATA_MISMATCH"
    INCOMPLETE = "INCOMPLETE"
    AMBIGUOUS = "AMBIGUOUS"
    CORRUPTED = "CORRUPTED"


@dataclass(frozen=True, slots=True)
class CsvTimeline:
    path: str
    first_mono_us: int | None = None
    last_mono_us: int | None = None
    rows: int = 0
    monotonic: bool = True
    error: str | None = None

    @property
    def duration_s(self) -> float | None:
        if self.first_mono_us is None or self.last_mono_us is None:
            return None
        return max(0.0, (self.last_mono_us - self.first_mono_us) / 1_000_000)


@dataclass(frozen=True, slots=True)
class SessionFacts:
    relative_path: str
    kind: UnitKind
    device_id: str | None = None
    object_id: str | None = None
    live_root: str | None = None
    capture_date: str | None = None
    created_epoch: float | None = None
    capture_t0_wall_s: float | None = None
    segment_start_wall: float | None = None
    segment_stop_wall: float | None = None
    claimed_video_duration_s: float | None = None
    sync_wall_s: float | None = None
    sync_ok: bool | None = None
    sync_fails: tuple[str, ...] = ()
    log_stop_durations_s: tuple[float, ...] = ()
    has_stop_log: bool = False
    restart_count: int = 0
    camera_dirs: tuple[str, ...] = ()
    mkv_paths: tuple[str, ...] = ()
    csv_timelines: tuple[CsvTimeline, ...] = ()
    missing_files: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Unit:
    path: Path
    facts: SessionFacts


@dataclass(frozen=True, slots=True)
class VideoEvidence:
    relative_path: str
    size_bytes: int
    packet_count: int
    pts_first_s: float | None
    pts_last_s: float | None
    duration_s: float | None
    frame_rate: float | None
    pts_monotonic: bool
    keyframes: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class Segment:
    unit_path: str
    camera: str
    video: VideoEvidence


@dataclass(frozen=True, slots=True)
class QRVerification:
    status: ResultStatus
    token_version: int | None = None
    token_id: str | None = None
    signer_device_id: str | None = None
    payload: dict[str, Any] | None = None
    source_video: str | None = None
    time_s: float | None = None
    votes: int = 0
    retired_device: bool = False
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Finding:
    code: ResultStatus
    severity: str
    subject: str
    message: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RecordingResult:
    recording_id: str
    unit_paths: tuple[str, ...]
    device_id: str | None
    created_epoch: float | None
    segments: tuple[Segment, ...]
    actual_duration_s: float | None
    status: ResultStatus
    trust_level: int
    reasons: tuple[str, ...] = ()
    qr: QRVerification | None = None


@dataclass(frozen=True, slots=True)
class VerificationReport:
    source_root: str
    run_id: str
    generated_at: str
    units: tuple[SessionFacts, ...]
    recordings: tuple[RecordingResult, ...]
    findings: tuple[Finding, ...] = field(default_factory=tuple)
