from pathlib import Path

import pytest

from zybtool import settings


def test_private_key_export_writes_hex_backup_without_overwrite(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        settings, "load_decoder_private_key", lambda: bytes.fromhex("0123456789abcdef" * 4)
    )
    destination = tmp_path / "decoder-private.key"
    exported = settings.export_decoder_private_key(destination)
    assert exported == destination
    assert destination.read_text(encoding="ascii") == "0123456789abcdef" * 4 + "\n"
    with pytest.raises(FileExistsError):
        settings.export_decoder_private_key(destination)
    assert destination.read_text(encoding="ascii") == "0123456789abcdef" * 4 + "\n"
