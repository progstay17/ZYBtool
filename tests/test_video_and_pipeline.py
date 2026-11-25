from pathlib import Path

import av
import pytest

from zybtool.pipeline import run_verification, write_report
from zybtool.videoscan import scan_video


def make_test_video(path: Path) -> None:
    container = av.open(str(path), mode="w")
    stream = container.add_stream("mpeg4", rate=10)
    stream.width = 96
    stream.height = 64
    stream.pix_fmt = "yuv420p"
    stream.codec_context.max_b_frames = 0

    for _ in range(20):
        frame = av.VideoFrame(96, 64, "yuv420p")
        for plane in frame.planes:
            plane.update(bytes(plane.buffer_size))
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def test_streaming_video_timeline(tmp_path: Path) -> None:
    video_path = tmp_path / "synthetic.mkv"
    make_test_video(video_path)

    evidence = scan_video(video_path)

    assert evidence.error is None
    assert evidence.packet_count == 20
    assert evidence.pts_monotonic is True
    assert evidence.duration_s == pytest.approx(2.0, abs=0.15)


def test_report_output_is_separate_and_complete(tmp_path: Path) -> None:
    fixtures = Path(__file__).parents[1] / "fixtures"
    output = tmp_path / "reports"
    report = run_verification(fixtures, allow_missing_media=True)
    destination = write_report(report, output)

    assert (destination / "inventory.json").is_file()
    assert (destination / "groups.json").is_file()
    assert (destination / "report.json").is_file()
    assert (destination / "report.html").is_file()
    assert (destination / "report.csv").is_file()


def test_report_must_not_be_written_inside_source(tmp_path: Path) -> None:
    fixtures = Path(__file__).parents[1] / "fixtures"
    report = run_verification(fixtures, allow_missing_media=True)

    with pytest.raises(ValueError):
        write_report(report, fixtures / "output")
