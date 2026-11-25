import os
from pathlib import Path

import pytest
from metaqr import generate_keypair

from zybtool import settings


def test_private_key_normalization_requires_32_bytes() -> None:
    assert settings._normalise_private_key("01 " * 32) == bytes.fromhex("01" * 32)
    with pytest.raises(ValueError):
        settings._normalise_private_key("abcd")


def test_dpapi_is_not_silently_replaced_on_non_windows(monkeypatch) -> None:
    monkeypatch.setattr(settings.os, "name", "posix")
    with pytest.raises(RuntimeError, match="Windows"):
        settings._dpapi(b"secret", decrypt=False)


def test_settings_path_can_be_redirected_for_tests(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ZYBTOOL_DATA_DIR", str(tmp_path))
    assert settings.data_dir() == tmp_path.resolve()


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI only")
def test_decoder_key_dpapi_round_trip_and_no_plaintext_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ZYBTOOL_DATA_DIR", str(tmp_path))
    keypair = generate_keypair()
    public_hex = settings.set_decoder_private_key(keypair.private)
    assert public_hex == keypair.public.hex()
    assert settings.load_decoder_private_key() == keypair.private
    raw_config = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert keypair.private.hex() not in raw_config
    settings.remove_decoder_private_key()
    with pytest.raises(RuntimeError, match="belum diatur"):
        settings.load_decoder_private_key()


def test_decoder_key_generation_refuses_to_replace_existing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ZYBTOOL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "_dpapi", lambda data, *, decrypt: b"protected")
    first_public_hex = settings.generate_decoder_keypair()
    original_document = settings._load_document()

    with pytest.raises(RuntimeError, match="sudah tersedia"):
        settings.generate_decoder_keypair()

    with pytest.raises(RuntimeError, match="sudah tersedia"):
        settings.set_decoder_private_key(generate_keypair().private)

    current_document = settings._load_document()
    assert current_document == original_document
    assert len(first_public_hex) == 64
