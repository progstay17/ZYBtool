"""Optional smoke checks against a caller-provided local recordings folder."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from zybtool.models import ResultStatus
from zybtool.pipeline import run_verification

pytestmark = pytest.mark.integration
SAMPLES_ROOT = os.environ.get("ZYB_SAMPLES_DIR")


@pytest.mark.skipif(not SAMPLES_ROOT, reason="Set ZYB_SAMPLES_DIR to a local fixture folder")
def test_external_sample_folder_is_scanned_read_only() -> None:
    report = run_verification(Path(SAMPLES_ROOT or ""), allow_missing_media=True)
    assert report.recordings
    assert all(item.status is not ResultStatus.VERIFIED for item in report.recordings)
