"""Streaming video timeline inspection using PyAV."""

from __future__ import annotations

import statistics
from pathlib import Path

import av

from zybtool.models import VideoEvidence


def scan_video(path: Path, relative_path: str | None = None) -> VideoEvidence:
    """Demux a video without decoding all frames or loading it into memory."""
    rel = relative_path or path.name
    try:
        size = path.stat().st_size
    except OSError as exc:
        return VideoEvidence(rel, 0, 0, None, None, None, None, False, 0, str(exc))
    try:
        with av.open(str(path), mode="r") as container:
            stream = next((item for item in container.streams if item.type == "video"), None)
            if stream is None:
                return VideoEvidence(
                    rel, size, 0, None, None, None, None, False, 0, "Video stream tidak ditemukan"
                )
            first_pts: float | None = None
            last_pts: float | None = None
            last_delta: float | None = None
            last_packet_duration: float | None = None
            packet_count = 0
            keyframes = 0
            monotonic = True

            for packet in container.demux(stream):
                if packet.pts is None:
                    continue
                current = float(packet.pts * packet.time_base)
                if first_pts is None:
                    first_pts = current
                if last_pts is not None:
                    delta = current - last_pts
                    if delta < 0:
                        monotonic = False
                    elif delta > 0:
                        last_delta = delta
                if packet.duration and packet.duration > 0:
                    last_packet_duration = float(packet.duration * packet.time_base)
                last_pts = current
                packet_count += 1
                if packet.is_keyframe:
                    keyframes += 1

            if packet_count == 0 or first_pts is None or last_pts is None:
                return VideoEvidence(
                    rel,
                    size,
                    packet_count,
                    None,
                    None,
                    None,
                    None,
                    False,
                    keyframes,
                    "Tidak ada paket video bertimestamp",
                )
            if not monotonic:
                return VideoEvidence(
                    rel,
                    size,
                    packet_count,
                    first_pts,
                    last_pts,
                    None,
                    None,
                    False,
                    keyframes,
                    "PTS tidak monoton",
                )

            interval = last_packet_duration or last_delta
            if not interval:
                rate = stream.average_rate
                interval = float(1 / rate) if rate else None
            if not interval or interval <= 0:
                return VideoEvidence(
                    rel,
                    size,
                    packet_count,
                    first_pts,
                    last_pts,
                    None,
                    None,
                    True,
                    keyframes,
                    "Interval frame terakhir tidak dapat ditentukan",
                )

            duration = max(0.0, last_pts - first_pts + interval)
            rate_value = float(stream.average_rate) if stream.average_rate else None
            return VideoEvidence(
                rel,
                size,
                packet_count,
                first_pts,
                last_pts,
                duration,
                rate_value,
                True,
                keyframes,
                None,
            )
    except Exception as exc:  # PyAV exposes several FFmpeg exception subclasses
        return VideoEvidence(
            rel,
            size,
            0,
            None,
            None,
            None,
            None,
            False,
            0,
            f"Gagal demux ({type(exc).__name__})",
        )


def median_duration(values: list[float]) -> float | None:
    """Small helper kept deterministic for tests and later calibration."""
    return statistics.median(values) if values else None
