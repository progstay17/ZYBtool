"""DPAPI-protected per-user decoder settings and trusted Metaqr allow-list."""

from __future__ import annotations

import base64
import contextlib
import ctypes
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


APP_ENTROPY = b"ZYBTool|Metaqr decoder private key|v1"
SETTINGS_VERSION = 1


def data_dir() -> Path:
    override = os.environ.get("ZYBTOOL_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        raise RuntimeError(
            "LOCALAPPDATA Windows tidak tersedia; penyimpanan kunci DPAPI tidak dapat dipakai."
        )
    return Path(root) / "ZYBTool"


def _blob(data: bytes) -> tuple[_DataBlob, Any]:
    buffer = ctypes.create_string_buffer(data, len(data))
    value = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    return value, buffer


def _dpapi(data: bytes, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Private key hanya dapat disimpan di Windows dengan DPAPI.")
    source, source_buffer = _blob(data)
    entropy, entropy_buffer = _blob(APP_ENTROPY)
    output = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.c_wchar_p,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = ctypes.c_bool
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(ctypes.c_wchar_p),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = ctypes.c_bool
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    flags = 0x1  # CRYPTPROTECT_UI_FORBIDDEN
    if decrypt:
        description = ctypes.c_wchar_p()
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(source),
            ctypes.byref(description),
            ctypes.byref(entropy),
            None,
            None,
            flags,
            ctypes.byref(output),
        )
    else:
        ok = crypt32.CryptProtectData(
            ctypes.byref(source),
            "ZYBTool decoder key",
            ctypes.byref(entropy),
            None,
            None,
            flags,
            ctypes.byref(output),
        )
    # Keep both buffers alive through the native call.
    _ = source_buffer, entropy_buffer
    if not ok:
        error = ctypes.get_last_error()
        raise OSError(error, f"Windows DPAPI gagal ({error}).")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


def _settings_path() -> Path:
    return data_dir() / "settings.json"


def _load_document() -> dict[str, Any]:
    path = _settings_path()
    if not path.exists():
        return {"version": SETTINGS_VERSION}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"File pengaturan rusak: {type(exc).__name__}") from None
    if not isinstance(value, dict) or value.get("version") != SETTINGS_VERSION:
        raise RuntimeError("Versi file pengaturan tidak dikenal.")
    return value


def _save_document(value: dict[str, Any]) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="settings.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def _normalise_private_key(value: str | bytes) -> bytes:
    try:
        raw = value if isinstance(value, bytes) else bytes.fromhex("".join(value.split()))
    except ValueError:
        raise ValueError("Key decoder harus berupa 64 karakter hex (32 byte).") from None
    if len(raw) != 32:
        raise ValueError(f"Private key decoder harus 32 byte; diterima {len(raw)} byte.")
    return raw


def set_decoder_private_key(value: str | bytes) -> str:
    """Validate and protect an X25519 private key; return its public-key fingerprint."""
    from metaqr import fingerprint, public_from_private

    private_key = _normalise_private_key(value)
    document = _load_document()
    if isinstance(document.get("decoder_private_key_dpapi"), str):
        raise RuntimeError(
            "Decoder key sudah tersedia. Hapus key lama secara eksplisit sebelum menggantinya."
        )
    public_key = public_from_private(private_key)
    protected = _dpapi(private_key, decrypt=False)
    document["decoder_private_key_dpapi"] = base64.b64encode(protected).decode("ascii")
    document["decoder_public_fingerprint"] = fingerprint(public_key)
    _save_document(document)
    return public_key.hex()


def generate_decoder_keypair() -> str:
    """Create the local decoder pair once; never replace an existing private key."""
    from metaqr import generate_keypair

    document = _load_document()
    if isinstance(document.get("decoder_private_key_dpapi"), str):
        raise RuntimeError(
            "Decoder key sudah tersedia. Pembuatan ulang diblokir agar QR lama tetap dapat didekripsi."
        )
    keypair = generate_keypair()
    return set_decoder_private_key(keypair.private)


def load_decoder_private_key() -> bytes:
    from metaqr import fingerprint, public_from_private

    document = _load_document()
    encoded = document.get("decoder_private_key_dpapi")
    expected = document.get("decoder_public_fingerprint")
    if not isinstance(encoded, str) or not isinstance(expected, str):
        raise RuntimeError(
            "Private decoder key belum diatur. Jalankan 'zybtool settings set-decoder-key'."
        )
    try:
        protected = base64.b64decode(encoded, validate=True)
        private_key = _dpapi(protected, decrypt=True)
    except (ValueError, OSError) as exc:
        raise RuntimeError(f"Private decoder key tidak dapat dibuka: {exc}") from None
    private_key = _normalise_private_key(private_key)
    if fingerprint(public_from_private(private_key)) != expected:
        raise RuntimeError("Fingerprint decoder key tidak cocok; pengaturan ditolak.")
    return private_key


def decoder_public_key_hex() -> str:
    from metaqr import public_from_private

    return public_from_private(load_decoder_private_key()).hex()


def import_allowlist(source: Path | str) -> tuple[Path, int]:
    from metaqr import Allowlist

    source_path = Path(source).expanduser().resolve(strict=True)
    allowlist = Allowlist.load(source_path)
    destination = data_dir() / "allowlist.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(allowlist.to_dict(), indent=2, ensure_ascii=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix="allowlist.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(temporary, destination)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise
    return destination, len(allowlist)


def load_allowlist() -> Any:
    from metaqr import Allowlist

    path = data_dir() / "allowlist.json"
    if not path.is_file():
        raise RuntimeError(
            "Allow-list MQ2 belum diimpor. Jalankan 'zybtool settings import-allowlist <file>'."
        )
    return Allowlist.load(path)


def settings_status() -> dict[str, Any]:
    document = _load_document()
    path = data_dir() / "allowlist.json"
    devices = 0
    if path.is_file():
        from metaqr import Allowlist

        devices = len(Allowlist.load(path))
    return {
        "decoder_key_configured": isinstance(document.get("decoder_private_key_dpapi"), str),
        "decoder_public_fingerprint": document.get("decoder_public_fingerprint"),
        "allowlist_configured": path.is_file(),
        "trusted_devices": devices,
        "storage": str(data_dir()),
    }


def remove_decoder_private_key() -> None:
    document = _load_document()
    document.pop("decoder_private_key_dpapi", None)
    document.pop("decoder_public_fingerprint", None)
    _save_document(document)
