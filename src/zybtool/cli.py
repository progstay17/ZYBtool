"""Command-line interface for ZYB Tool."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from zybtool import __version__
from zybtool.models import ResultStatus
from zybtool.pipeline import run_verification, write_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zybtool",
        description="Verifikasi recording BLACK secara lokal dan read-only.",
    )
    parser.add_argument("--version", action="version", version=f"ZYB Tool {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="Temukan, periksa dan laporkan recording")
    scan.add_argument("source", type=Path, help="Folder recording sumber (tidak diubah)")
    scan.add_argument(
        "--output", type=Path, required=True, help="Folder terpisah untuk artefak laporan"
    )

    settings = commands.add_parser("settings", help="Pengaturan key decoder dan allow-list Metaqr")
    settings_commands = settings.add_subparsers(dest="settings_command", required=True)
    settings_commands.add_parser(
        "show", help="Tampilkan status pengaturan tanpa menampilkan key privat"
    )
    settings_commands.add_parser(
        "generate-decoder-key",
        help="Buat pasangan key decoder lokal dan simpan privat dengan DPAPI",
    )
    settings_commands.add_parser(
        "set-decoder-key", help="Impor private key X25519 secara tersembunyi"
    )
    settings_commands.add_parser(
        "export-public-key", help="Tampilkan public key untuk dipasang di AITQR"
    )
    import_allowlist = settings_commands.add_parser(
        "import-allowlist", help="Impor allow-list perangkat MQ2"
    )
    import_allowlist.add_argument("file", type=Path)
    settings_commands.add_parser("remove-decoder-key", help="Hapus private decoder key tersimpan")

    return parser


def _run_settings(command: str, file: Path | None = None) -> int:
    from zybtool.settings import (
        decoder_public_key_hex,
        generate_decoder_keypair,
        import_allowlist,
        remove_decoder_private_key,
        set_decoder_private_key,
        settings_status,
    )

    if command == "show":
        print(json.dumps(settings_status(), indent=2, ensure_ascii=False))
        return 0
    if command == "generate-decoder-key":
        public_hex = generate_decoder_keypair()
        print("Decoder key berhasil dibuat dan private key disimpan dengan Windows DPAPI.")
        print(f"Public key untuk AITQR: {public_hex}")
        print("Simpan public key ini di AITQR. Jangan pernah mengirim private key.")
        return 0
    if command == "set-decoder-key":
        first = getpass.getpass("Private decoder key X25519 (64 karakter hex): ")
        second = getpass.getpass("Ulangi private decoder key: ")
        if first.strip() != second.strip():
            print("Key tidak sama; pengaturan dibatalkan.", file=sys.stderr)
            return 2
        public_hex = set_decoder_private_key(first)
        print("Private decoder key tersimpan dengan Windows DPAPI.")
        print(f"Fingerprint/public key pasangan: {public_hex}")
        return 0
    if command == "export-public-key":
        print(decoder_public_key_hex())
        return 0
    if command == "import-allowlist":
        if file is None:
            raise ValueError("File allow-list harus ditentukan.")
        path, count = import_allowlist(file)
        print(f"Allow-list diimpor: {count} perangkat tepercaya.")
        print(f"Lokasi: {path}")
        return 0
    if command == "remove-decoder-key":
        remove_decoder_private_key()
        print("Private decoder key dihapus dari penyimpanan DPAPI.")
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "settings":
        try:
            return _run_settings(args.settings_command, getattr(args, "file", None))
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"Gagal: {exc}", file=sys.stderr)
            return 2

    if args.command == "scan":
        try:
            report = run_verification(args.source)
            destination = write_report(report, args.output)
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"Gagal: {exc}", file=sys.stderr)
            return 2

        counts = {status: 0 for status in ResultStatus}
        for item in report.recordings:
            counts[item.status] += 1
        print("ZYB Tool - hasil pemindaian")
        print(f"Sumber       : {report.source_root}")
        print(f"Run ID       : {report.run_id}")
        print(f"Unit         : {len(report.units)}")
        print(f"Recording    : {len(report.recordings)}")
        for status, count in counts.items():
            if count:
                print(f"{status.value:24} {count}")
        print(f"Laporan      : {destination}")
        print("Catatan      : Folder sumber tetap read-only; upload OSS belum aktif.")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
