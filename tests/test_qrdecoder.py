from pathlib import Path

import cv2
import metaqr
import numpy as np
import pytest
from metaqr.qr import render

from zybtool.qrdecoder import decode_qr_image, decode_token


def _payload() -> dict[str, object]:
    return {
        "p": "zyb-recording",
        "pv": 1,
        "s": "0123456789ABCDEF",
        "r": "BLACK",
        "dn": "ZY010",
        "di": "fixture-device-001",
        "l": "SITE01",
        "a": "Activity",
        "sh": 1,
        "b": "MM01",
    }


def test_decode_token_returns_validated_json_payload() -> None:
    keypair = metaqr.generate_keypair()
    token = metaqr.encode(_payload(), keypair.public)
    assert decode_token(token, keypair.private) == _payload()


def test_decode_token_rejects_wrong_private_key() -> None:
    sender = metaqr.generate_keypair()
    wrong_key = metaqr.generate_keypair()
    token = metaqr.encode(_payload(), sender.public)
    with pytest.raises(ValueError, match="Dekripsi MQ1 gagal"):
        decode_token(token, wrong_key.private)


def test_decode_token_rejects_non_contract_payload() -> None:
    keypair = metaqr.generate_keypair()
    token = metaqr.encode({"unexpected": True}, keypair.public)
    with pytest.raises(ValueError, match="Payload terdekripsi tetapi tidak valid"):
        decode_token(token, keypair.private)


def test_decode_qr_image_scans_and_decrypts(tmp_path: Path) -> None:
    keypair = metaqr.generate_keypair()
    token = metaqr.encode(_payload(), keypair.public)
    image_path = tmp_path / "aitqr.png"
    assert cv2.imwrite(str(image_path), render(token, scale=4))
    scanned_token, payload = decode_qr_image(image_path, private_key=keypair.private)
    assert scanned_token == token
    assert payload == _payload()


def test_decode_qr_image_rejects_non_qr_image(tmp_path: Path) -> None:
    image_path = tmp_path / "blank.png"
    assert cv2.imwrite(str(image_path), np.zeros((100, 100, 3), dtype="uint8"))
    with pytest.raises(ValueError, match="QR Metaqr tidak ditemukan"):
        decode_qr_image(image_path, private_key=metaqr.generate_keypair().private)
