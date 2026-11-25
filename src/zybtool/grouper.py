"""Conservative segment grouping; no guesswork from filenames or time proximity."""

from __future__ import annotations

import hashlib
from pathlib import Path

from zybtool.models import RecordingResult, Segment, Unit, UnitKind, VideoEvidence
from zybtool.status import evaluate_status
from zybtool.util import sha256_file


def _recording_id(unit: Unit) -> str:
    facts = unit.facts
    identity_parts = (
        facts.device_id or "",
        facts.object_id or "",
        str(facts.capture_t0_wall_s or ""),
    )
    identity = "|".join(identity_parts + (facts.relative_path if not all(identity_parts) else "",))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _same_media(left: Unit, right: Unit) -> bool:
    left_paths = {Path(value).name: left.path / Path(value) for value in left.facts.mkv_paths}
    right_paths = {Path(value).name: right.path / Path(value) for value in right.facts.mkv_paths}
    if not left_paths or set(left_paths) != set(right_paths):
        return False
    for name in sorted(left_paths):
        a, b = left_paths[name], right_paths[name]
        try:
            if a.stat().st_size != b.stat().st_size:
                return False
            if sha256_file(a) != sha256_file(b):
                return False
        except OSError:
            return False
    return True


def _link_candidate(final: Unit, live: Unit) -> bool:
    a, b = final.facts, live.facts
    return bool(
        a.kind is UnitKind.FINAL
        and b.kind is UnitKind.LIVE
        and a.device_id
        and a.device_id == b.device_id
        and a.live_root
        and a.live_root == live.path.name
        and a.created_epoch is not None
        and b.created_epoch is not None
        and abs(a.created_epoch - b.created_epoch) <= 2.0
    )


def _segments_for_unit(
    unit: Unit,
    evidence: dict[str, VideoEvidence],
) -> tuple[Segment, ...]:
    results: list[Segment] = []
    for relative in unit.facts.mkv_paths:
        path = (unit.path / Path(relative)).resolve()
        video = evidence.get(str(path))
        if video is None:
            continue
        camera = Path(relative).parent.as_posix()
        results.append(Segment(unit.facts.relative_path, camera, video))
    return tuple(
        sorted(results, key=lambda item: (item.camera.lower(), item.video.relative_path.lower()))
    )


def _duration(segments: tuple[Segment, ...]) -> float | None:
    by_camera: dict[str, list[float]] = {}
    for segment in segments:
        if segment.video.duration_s is not None:
            by_camera.setdefault(segment.camera, []).append(segment.video.duration_s)
    totals = [sum(values) for values in by_camera.values()]
    return max(totals) if totals else None


def group_recordings(
    units: tuple[Unit, ...],
    evidence: dict[str, VideoEvidence],
    *,
    allow_missing_media: bool = False,
) -> tuple[RecordingResult, ...]:
    """Group only proven FINAL/LIVE duplicates; conflicting matches stay ambiguous."""
    ordered = tuple(sorted(units, key=lambda u: u.facts.relative_path.lower()))
    attached: dict[str, tuple[str, ...]] = {}
    ambiguous_paths: set[str] = set()
    consumed_live: set[str] = set()

    finals = [unit for unit in ordered if unit.facts.kind is UnitKind.FINAL]
    lives = [unit for unit in ordered if unit.facts.kind is UnitKind.LIVE]
    for live in lives:
        candidates = [final for final in finals if _link_candidate(final, live)]
        if len(candidates) > 1:
            ambiguous_paths.add(live.facts.relative_path)
            ambiguous_paths.update(item.facts.relative_path for item in candidates)
            continue
        if len(candidates) == 1:
            final = candidates[0]
            if _same_media(final, live):
                attached[final.facts.relative_path] = (
                    *attached.get(final.facts.relative_path, ()),
                    live.facts.relative_path,
                )
                consumed_live.add(live.facts.relative_path)
            else:
                ambiguous_paths.add(final.facts.relative_path)
                ambiguous_paths.add(live.facts.relative_path)

    results: list[RecordingResult] = []
    for unit in ordered:
        relative = unit.facts.relative_path
        if relative in consumed_live:
            continue
        linked_paths = attached.get(relative, ())
        member_units = (unit,) + tuple(
            next(item for item in ordered if item.facts.relative_path == path)
            for path in linked_paths
        )
        member_facts = tuple(item.facts for item in member_units)
        segments = tuple(
            segment for member in member_units for segment in _segments_for_unit(member, evidence)
        )
        ambiguous = relative in ambiguous_paths
        status_facts = (unit.facts,) if linked_paths else member_facts
        status, level, reasons = evaluate_status(
            status_facts,
            segments,
            ambiguous=ambiguous,
            allow_missing_media=allow_missing_media,
        )
        results.append(
            RecordingResult(
                recording_id=_recording_id(unit),
                unit_paths=tuple(item.facts.relative_path for item in member_units),
                device_id=unit.facts.device_id,
                created_epoch=unit.facts.created_epoch,
                segments=segments,
                actual_duration_s=_duration(segments),
                status=status,
                trust_level=level,
                reasons=reasons,
            )
        )
    return tuple(
        sorted(
            results,
            key=lambda item: (item.device_id or "", item.created_epoch or 0, item.recording_id),
        )
    )
