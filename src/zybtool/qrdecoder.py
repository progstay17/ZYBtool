"""Local AITQR MQ1 token and QR-image decoder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import metaqr
from metaqr.errors import MetaQRError
from metaqr.qr import find_token

from zybtool.settings import load_decoder_private_key


def decode_token(token: str, private_key: bytes) -> dict[str, Any]:
    """Decrypt an MQ1 token and return its original JSON object without imposing a schema."""
    normalized = token.strip()
    if not normalized:
        raise ValueError("Token kosong.")
    try:
        version = metaqr.token_version(normalized)
    except MetaQRError as exc:
        raise ValueError(f"Format token Metaqr tidak valid: {exc}") from None
    if version != 1:
        raise ValueError(
            f"Token MQ{version} tidak didukung. AITQR harus menerbitkan token terenkripsi MQ1."
        )
    try:
        payload = metaqr.decode(normalized, private_key)
    except MetaQRError:
        raise ValueError(
            "Dekripsi MQ1 gagal. Pastikan token utuh dan private key yang terpasang cocok."
        ) from None
    if not isinstance(payload, dict):
        raise ValueError("Isi token terdekripsi bukan JSON object.")
    return payload


def decode_token_with_saved_key(token: str) -> dict[str, Any]:
    """Decrypt using this Windows user's DPAPI-protected decoder private key."""
    return decode_token(token, load_decoder_private_key())


def decode_qr_image(
    image_path: Path | str, *, private_key: bytes | None = None
) -> tuple[str, dict[str, Any]]:
    """Read one QR token from an image and decrypt it locally."""
    path = Path(image_path).expanduser()
    if not path.is_file():
        raise ValueError(f"File gambar tidak ditemukan: {path}")
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Gambar tidak dapat dibaca. Gunakan PNG, JPG, JPEG, BMP, atau WebP.")
    token = find_token(image)
    if not token:
        raise ValueError("QR Metaqr tidak ditemukan pada gambar.")
    key = private_key if private_key is not None else load_decoder_private_key()
    return token, decode_token(token, key)
