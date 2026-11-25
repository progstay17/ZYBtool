"""Tkinter desktop shell and Security & Keys settings for ZYB Tool."""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from zybtool import __version__
from zybtool.settings import (
    data_dir,
    decoder_public_key_hex,
    generate_decoder_keypair,
    import_allowlist,
    remove_decoder_private_key,
    set_decoder_private_key,
    settings_status,
)

BG = "#080D0B"
SIDEBAR = "#0E1511"
SURFACE = "#131D17"
SURFACE_HOVER = "#19251D"
LINE = "#26372C"
TEXT = "#E8F0E9"
SECONDARY = "#A0B0A4"
MUTED = "#718176"
GREEN = "#A3F36B"
GREEN_DARK = "#5DBB45"
AMBER = "#F2B84B"
RED = "#FF6B68"
BLUE = "#77B9D8"
FONT = "Segoe UI"
MONO = "Consolas"


class ZYBToolApp:
    """Small desktop shell focused on the implemented Settings workflow."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("ZYBTool")
        self.root.configure(bg=BG)
        self.root.geometry("1260x820")
        self.root.minsize(1024, 700)
        self.root.option_add("*Font", (FONT, 10))
        self.status_var = tk.StringVar(value="Memuat status pengaturan…")
        self.key_state_var = tk.StringVar(value="Memeriksa…")
        self.key_detail_var = tk.StringVar(value="")
        self.public_key_var = tk.StringVar(value="")
        self.allowlist_state_var = tk.StringVar(value="Memeriksa…")
        self.allowlist_detail_var = tk.StringVar(value="")
        self.storage_var = tk.StringVar(value=str(data_dir()))
        self.generate_button: tk.Button | None = None
        self.import_button: tk.Button | None = None
        self.copy_button: tk.Button | None = None
        self.remove_button: tk.Button | None = None
        self.public_entry: tk.Entry | None = None
        self._build_styles()
        self._build_shell()
        self.refresh()

    def _build_styles(self) -> None:
        style = ttk.Style(self.root)
        with contextlib.suppress(tk.TclError):
            style.theme_use("clam")
        style.configure(
            "ZYB.Vertical.TScrollbar",
            background=SURFACE,
            troughcolor=BG,
            bordercolor=BG,
            arrowcolor=SECONDARY,
        )

    def _build_shell(self) -> None:
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        sidebar = tk.Frame(self.root, bg=SIDEBAR, width=236)
        sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        sidebar.grid_propagate(False)

        brand = tk.Frame(sidebar, bg=SIDEBAR)
        brand.pack(fill="x", padx=22, pady=(24, 30))
        tk.Label(brand, text="ZYB", bg=SIDEBAR, fg=GREEN, font=(FONT, 22, "bold")).pack(anchor="w")
        tk.Label(
            brand, text="FIELD DATA OPERATIONS", bg=SIDEBAR, fg=SECONDARY, font=(FONT, 8, "bold")
        ).pack(anchor="w", pady=(2, 0))
        tk.Frame(sidebar, bg=LINE, height=1).pack(fill="x", padx=16, pady=(0, 22))

        tk.Label(sidebar, text="WORKSPACE", bg=SIDEBAR, fg=MUTED, font=(FONT, 8, "bold")).pack(
            anchor="w", padx=22, pady=(0, 10)
        )

        nav_items = [
            ("Overview", False),
            ("Verify Recordings", False),
            ("Review Queue", False),
            ("Output & Reports", False),
            ("OSS Transfers", False),
            ("Activity Log", False),
        ]
        for label, enabled in nav_items:
            button = tk.Button(
                sidebar,
                text=f"   {label}",
                anchor="w",
                relief="flat",
                bd=0,
                padx=12,
                pady=11,
                bg=SIDEBAR,
                fg=SECONDARY if enabled else MUTED,
                activebackground=SURFACE_HOVER,
                activeforeground=TEXT,
                state="normal" if enabled else "disabled",
                disabledforeground="#526157",
                font=(FONT, 10),
                cursor="arrow",
            )
            button.pack(fill="x", padx=12, pady=1)

        selected = tk.Frame(sidebar, bg=SURFACE_HOVER)
        selected.pack(fill="x", padx=12, pady=(14, 1))
        tk.Frame(selected, bg=GREEN, width=3).pack(side="left", fill="y")
        tk.Label(
            selected,
            text="   Settings",
            anchor="w",
            padx=9,
            pady=11,
            bg=SURFACE_HOVER,
            fg=GREEN,
            font=(FONT, 10, "bold"),
        ).pack(side="left", fill="x", expand=True)

        tk.Frame(sidebar, bg=LINE, height=1).pack(side="bottom", fill="x", padx=16, pady=(0, 14))
        tk.Label(
            sidebar,
            text="Fadhil Ghifarion " + chr(0x6CD5) + chr(0x8FEA) + " for AIT",
            bg=SIDEBAR,
            fg=SECONDARY,
            font=(FONT, 8, "bold"),
        ).pack(side="bottom", anchor="w", padx=22, pady=(0, 4))
        tk.Label(
            sidebar, text=f"ZYBTool  v{__version__}", bg=SIDEBAR, fg=MUTED, font=(MONO, 8)
        ).pack(side="bottom", anchor="w", padx=22, pady=(0, 8))

        topbar = tk.Frame(self.root, bg=BG, height=62)
        topbar.grid(row=0, column=1, sticky="ew")
        topbar.grid_propagate(False)
        tk.Label(topbar, text="ZYB TOOL  /  SETTINGS", bg=BG, fg=MUTED, font=(MONO, 9)).pack(
            side="left", padx=28, pady=22
        )
        tk.Label(
            topbar, text="LOCAL WORKSTATION", bg=BG, fg=SECONDARY, font=(FONT, 8, "bold")
        ).pack(side="right", padx=28, pady=22)

        tk.Frame(self.root, bg=LINE, height=1).grid(row=0, column=1, sticky="sew")

        content_host = tk.Frame(self.root, bg=BG)
        content_host.grid(row=1, column=1, sticky="nsew")
        content_host.grid_rowconfigure(0, weight=1)
        content_host.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(content_host, bg=BG, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(
            content_host, orient="vertical", command=canvas.yview, style="ZYB.Vertical.TScrollbar"
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.content = tk.Frame(canvas, bg=BG)
        window_id = canvas.create_window((0, 0), window=self.content, anchor="nw")

        def update_scroll_region(_: tk.Event[Any] | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def resize_content(event: tk.Event[Any]) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        self.content.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", resize_content)
        canvas.bind_all(
            "<MouseWheel>", lambda event: canvas.yview_scroll(int(-event.delta / 120), "units")
        )

        self._build_settings_content()

        statusbar = tk.Frame(self.root, bg=SIDEBAR, height=30)
        statusbar.grid(row=2, column=0, columnspan=2, sticky="ew")
        statusbar.grid_propagate(False)
        tk.Label(
            statusbar,
            textvariable=self.status_var,
            bg=SIDEBAR,
            fg=SECONDARY,
            font=(FONT, 9),
            anchor="w",
        ).pack(fill="both", padx=18)

    def _build_settings_content(self) -> None:
        page = self.content
        page.grid_columnconfigure(0, weight=1)

        header = tk.Frame(page, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=34, pady=(28, 22))
        tk.Label(header, text="Settings", bg=BG, fg=TEXT, font=(FONT, 25, "bold")).pack(anchor="w")
        tk.Label(
            header,
            text="Kelola identitas decoder dan perangkat AITQR yang dipercaya.",
            bg=BG,
            fg=SECONDARY,
            font=(FONT, 10),
        ).pack(anchor="w", pady=(6, 0))

        section = tk.Frame(page, bg=BG)
        section.grid(row=1, column=0, sticky="ew", padx=34)
        tk.Label(section, text="SECURITY & KEYS", bg=BG, fg=GREEN, font=(FONT, 9, "bold")).pack(
            anchor="w"
        )
        tk.Frame(section, bg=LINE, height=1).pack(fill="x", pady=(10, 16))

        grid = tk.Frame(page, bg=BG)
        grid.grid(row=2, column=0, sticky="ew", padx=34)
        grid.grid_columnconfigure(0, weight=3)
        grid.grid_columnconfigure(1, weight=2)

        key_card = self._card(grid)
        key_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 14))
        allow_card = self._card(grid)
        allow_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=(0, 14))

        self._card_title(key_card, "Decoder keypair", "X25519 · dekripsi QR MQ2")
        key_state = tk.Frame(key_card, bg=SURFACE)
        key_state.pack(fill="x", pady=(16, 12))
        tk.Label(
            key_state,
            textvariable=self.key_state_var,
            bg=SURFACE,
            fg=GREEN,
            font=(FONT, 11, "bold"),
        ).pack(anchor="w")
        tk.Label(
            key_state,
            textvariable=self.key_detail_var,
            bg=SURFACE,
            fg=SECONDARY,
            font=(FONT, 9),
            justify="left",
            wraplength=500,
        ).pack(anchor="w", pady=(4, 0))

        tk.Label(
            key_card,
            text="PUBLIC KEY  /  UNTUK AITQR",
            bg=SURFACE,
            fg=MUTED,
            font=(FONT, 8, "bold"),
        ).pack(anchor="w", pady=(8, 7))
        entry_row = tk.Frame(key_card, bg=SURFACE)
        entry_row.pack(fill="x")
        self.public_entry = tk.Entry(
            entry_row,
            textvariable=self.public_key_var,
            state="readonly",
            readonlybackground="#0A100D",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            font=(MONO, 9),
            highlightthickness=1,
            highlightbackground=LINE,
            highlightcolor=GREEN,
        )
        self.public_entry.pack(side="left", fill="x", expand=True, ipady=11, padx=(0, 8))
        self.copy_button = self._button(
            entry_row, "Copy public key", self.copy_public_key, primary=False
        )
        self.copy_button.pack(side="right", fill="y")

        action_row = tk.Frame(key_card, bg=SURFACE)
        action_row.pack(fill="x", pady=(16, 0))
        self.generate_button = self._button(
            action_row, "Generate decoder key", self.generate_key, primary=True
        )
        self.generate_button.pack(side="left")
        self.import_button = self._button(
            action_row, "Import private key", self.import_private_key, primary=False
        )
        self.import_button.pack(side="left", padx=(8, 0))
        self.remove_button = self._button(action_row, "Remove key", self.remove_key, danger=True)
        self.remove_button.pack(side="left", padx=(8, 0))

        self._card_title(
            allow_card, "Trusted devices · Optional", "Ed25519 · verifikasi tanda tangan MQ2"
        )
        tk.Label(
            allow_card,
            textvariable=self.allowlist_state_var,
            bg=SURFACE,
            fg=TEXT,
            font=(FONT, 15, "bold"),
        ).pack(anchor="w", pady=(22, 4))
        tk.Label(
            allow_card,
            textvariable=self.allowlist_detail_var,
            bg=SURFACE,
            fg=SECONDARY,
            font=(FONT, 9),
            wraplength=280,
            justify="left",
        ).pack(anchor="w", pady=(0, 18))
        self._button(
            allow_card, "Import allow-list (optional)", self.choose_allowlist, primary=False
        ).pack(anchor="w")
        tk.Label(
            allow_card,
            text="Opsional. File JSON divalidasi oleh Metaqr sebelum disimpan lokal. Tidak diperlukan untuk membuka atau menjalankan ZYBTool.",
            bg=SURFACE,
            fg=MUTED,
            font=(FONT, 8),
            wraplength=280,
            justify="left",
        ).pack(anchor="w", pady=(12, 0))

        storage = self._card(page)
        storage.grid(row=3, column=0, sticky="ew", padx=34, pady=(2, 14))
        self._card_title(storage, "Local security storage", "Windows DPAPI · current Windows user")
        storage_row = tk.Frame(storage, bg=SURFACE)
        storage_row.pack(fill="x", pady=(16, 0))
        storage_text = tk.Frame(storage_row, bg=SURFACE)
        storage_text.pack(side="left", fill="x", expand=True)
        tk.Label(
            storage_text,
            text="APPLICATION DATA DIRECTORY",
            bg=SURFACE,
            fg=MUTED,
            font=(FONT, 8, "bold"),
        ).pack(anchor="w")
        tk.Label(
            storage_text,
            textvariable=self.storage_var,
            bg=SURFACE,
            fg=TEXT,
            font=(MONO, 9),
            wraplength=760,
            justify="left",
        ).pack(anchor="w", pady=(5, 0))
        self._button(storage_row, "Open folder", self.open_storage, primary=False).pack(
            side="right", padx=(12, 0)
        )

        notice = tk.Frame(page, bg="#111B15", highlightthickness=1, highlightbackground="#304A31")
        notice.grid(row=4, column=0, sticky="ew", padx=34, pady=(0, 28))
        tk.Label(notice, text="KEY HANDOFF", bg="#111B15", fg=GREEN, font=(FONT, 8, "bold")).pack(
            anchor="w", padx=16, pady=(13, 4)
        )
        tk.Label(
            notice,
            text=(
                "ZYBTool membuat pasangan X25519. Hanya public key di atas yang disalin "
                "ke AITQR untuk enkripsi. Private key tetap berada di PC ini dan dilindungi "
                "Windows DPAPI; jangan pernah mengirim atau menyalinnya ke AITQR."
            ),
            bg="#111B15",
            fg=TEXT,
            font=(FONT, 9),
            wraplength=900,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 13))

    @staticmethod
    def _card(parent: tk.Widget) -> tk.Frame:
        return tk.Frame(
            parent, bg=SURFACE, padx=20, pady=18, highlightthickness=1, highlightbackground=LINE
        )

    @staticmethod
    def _card_title(card: tk.Frame, title: str, subtitle: str) -> None:
        tk.Label(card, text=title, bg=SURFACE, fg=TEXT, font=(FONT, 13, "bold")).pack(anchor="w")
        tk.Label(card, text=subtitle, bg=SURFACE, fg=MUTED, font=(FONT, 9)).pack(
            anchor="w", pady=(4, 0)
        )

    @staticmethod
    def _button(
        parent: tk.Widget,
        label: str,
        command: Any,
        *,
        primary: bool = False,
        danger: bool = False,
    ) -> tk.Button:
        background = GREEN if primary else ("#3B1D1D" if danger else SURFACE_HOVER)
        foreground = BG if primary else (RED if danger else TEXT)
        active_background = GREEN_DARK if primary else ("#512525" if danger else "#223127")
        return tk.Button(
            parent,
            text=label,
            command=command,
            bg=background,
            fg=foreground,
            activebackground=active_background,
            activeforeground=foreground,
            disabledforeground=MUTED,
            relief="flat",
            bd=0,
            padx=14,
            pady=10,
            font=(FONT, 9, "bold"),
            cursor="hand2",
            highlightthickness=0,
        )

    def _set_status(self, message: str, *, error: bool = False) -> None:
        self.status_var.set(message)
        # Keep the status strip neutral; detailed failures are also shown in dialogs.
        _ = error

    def refresh(self) -> None:
        try:
            status = settings_status()
            self.storage_var.set(str(status["storage"]))
            if status["decoder_key_configured"]:
                public_key = decoder_public_key_hex()
                self.public_key_var.set(public_key)
                self.key_state_var.set("Decoder key siap")
                self.key_detail_var.set(
                    f"Fingerprint: {status.get('decoder_public_fingerprint') or 'tersedia'}\n"
                    "Private key terenkripsi dengan Windows DPAPI."
                )
                if self.generate_button is not None:
                    self.generate_button.configure(
                        text="Key already generated", state="disabled", cursor="arrow"
                    )
                if self.copy_button is not None:
                    self.copy_button.configure(state="normal")
                if self.remove_button is not None:
                    self.remove_button.configure(state="normal")
                if self.import_button is not None:
                    self.import_button.configure(state="disabled")
            else:
                self.public_key_var.set("")
                self.key_state_var.set("Decoder key belum dibuat")
                self.key_detail_var.set(
                    "Buat satu pasangan kunci di PC ini. Proses ini hanya dilakukan sekali "
                    "saat setup awal."
                )
                if self.generate_button is not None:
                    self.generate_button.configure(
                        text="Generate decoder key", state="normal", cursor="hand2"
                    )
                if self.copy_button is not None:
                    self.copy_button.configure(state="disabled")
                if self.remove_button is not None:
                    self.remove_button.configure(state="disabled")
                if self.import_button is not None:
                    self.import_button.configure(state="normal")

            if status["allowlist_configured"]:
                count = int(status["trusted_devices"])
                self.allowlist_state_var.set(f"{count} perangkat tepercaya")
                self.allowlist_detail_var.set(
                    "Allow-list aktif. Status tiap device tetap mengikuti entri Metaqr."
                )
            else:
                self.allowlist_state_var.set("Opsional — belum dikonfigurasi")
                self.allowlist_detail_var.set(
                    "ZYBTool tetap bisa digunakan tanpa pairing. Impor allow-list "
                    "Ed25519 kapan saja untuk memverifikasi tanda tangan perangkat AITQR. "
                    "Perangkat yang belum dipercaya tidak akan dianggap valid."
                )
            self._set_status("Pengaturan lokal berhasil dibaca.")
        except Exception as exc:
            self.key_state_var.set("Status pengaturan tidak dapat dibaca")
            self.key_detail_var.set(str(exc))
            self._set_status(f"Gagal membaca pengaturan: {exc}", error=True)

    def generate_key(self) -> None:
        try:
            current = settings_status()
            if current["decoder_key_configured"]:
                messagebox.showinfo(
                    "Decoder key sudah tersedia",
                    "ZYBTool sudah memiliki decoder key. Key tidak dibuat ulang agar QR "
                    "yang sudah diterbitkan tetap dapat didekripsi.",
                    parent=self.root,
                )
                self.refresh()
                return
            confirmed = messagebox.askyesno(
                "Generate decoder key",
                "ZYBTool akan membuat pasangan kunci X25519.\n\n"
                "Private key disimpan lokal dengan Windows DPAPI. Hanya public key "
                "yang akan diberikan ke AITQR.\n\nLanjutkan?",
                parent=self.root,
            )
            if not confirmed:
                return
            public_key = generate_decoder_keypair()
            self.refresh()
            self._set_status("Decoder key berhasil dibuat dan disimpan secara lokal.")
            messagebox.showinfo(
                "Decoder key berhasil dibuat",
                "Pasangan kunci berhasil disimpan.\n\n"
                "Langkah berikutnya: klik Copy public key, lalu masukkan public key itu "
                "ke konfigurasi AITQR. Jangan bagikan private key.",
                parent=self.root,
            )
            self.public_key_var.set(public_key)
        except Exception as exc:
            messagebox.showerror("Gagal membuat decoder key", str(exc), parent=self.root)
            self._set_status(f"Gagal membuat decoder key: {exc}", error=True)

    def import_private_key(self) -> None:
        """Import a recovery X25519 private key without exposing it in the UI."""
        try:
            current = settings_status()
            if current["decoder_key_configured"]:
                messagebox.showwarning(
                    "Decoder key sudah tersedia",
                    "Key yang sudah terpasang tidak dapat ditimpa. Hapus key lama secara "
                    "eksplisit setelah memastikan backup aman, lalu impor ulang.",
                    parent=self.root,
                )
                self.refresh()
                return
            first = simpledialog.askstring(
                "Import private decoder key",
                "Masukkan private key X25519 (64 karakter hexadecimal).\n"
                "Input disembunyikan dan tidak akan ditampilkan kembali:",
                show="*",
                parent=self.root,
            )
            if first is None:
                return
            second = simpledialog.askstring(
                "Konfirmasi private decoder key",
                "Masukkan ulang private key untuk memastikan tidak ada kesalahan:",
                show="*",
                parent=self.root,
            )
            if second is None:
                return
            if first.strip() != second.strip():
                messagebox.showerror(
                    "Konfirmasi tidak cocok",
                    "Kedua input private key berbeda. Tidak ada perubahan yang disimpan.",
                    parent=self.root,
                )
                return
            public_key = set_decoder_private_key(first)
            self.refresh()
            self.public_key_var.set(public_key)
            self._set_status("Private decoder key berhasil diimpor dan dilindungi DPAPI.")
            messagebox.showinfo(
                "Private key berhasil diimpor",
                "Key berhasil divalidasi dan disimpan dengan Windows DPAPI.\n\n"
                "Public key pasangannya sudah dimuat. Jangan bagikan private key.",
                parent=self.root,
            )
        except Exception as exc:
            messagebox.showerror(
                "Import private key gagal",
                str(exc),
                parent=self.root,
            )
            self._set_status(f"Import private key gagal: {exc}", error=True)

    def copy_public_key(self) -> None:
        value = self.public_key_var.get().strip()
        if not value:
            messagebox.showwarning(
                "Public key belum tersedia",
                "Buat decoder key terlebih dahulu.",
                parent=self.root,
            )
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()
        self._set_status("Public key disalin ke clipboard. Private key tidak disalin.")

    def choose_allowlist(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Pilih allow-list perangkat AITQR",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not selected:
            return
        try:
            destination, count = import_allowlist(Path(selected))
            self.refresh()
            self._set_status(f"Allow-list berhasil diimpor: {count} perangkat.")
            messagebox.showinfo(
                "Allow-list berhasil diimpor",
                f"{count} perangkat tepercaya dimuat.\n\nLokasi lokal:\n{destination}",
                parent=self.root,
            )
        except Exception as exc:
            messagebox.showerror(
                "Allow-list tidak dapat diimpor",
                str(exc),
                parent=self.root,
            )
            self._set_status(f"Impor allow-list gagal: {exc}", error=True)

    def remove_key(self) -> None:
        if not self.public_key_var.get():
            return
        confirmed = messagebox.askyesno(
            "Hapus decoder key?",
            "Tindakan ini menghapus private key lokal. QR lama yang dienkripsi "
            "untuk pasangan public key ini tidak dapat didekripsi lagi oleh ZYBTool.\n\n"
            "Pastikan Anda memiliki backup aman sebelum melanjutkan.\n\nHapus key?",
            icon="warning",
            parent=self.root,
        )
        if not confirmed:
            return
        try:
            remove_decoder_private_key()
            self.refresh()
            self._set_status("Decoder key lokal telah dihapus.")
        except Exception as exc:
            messagebox.showerror("Gagal menghapus key", str(exc), parent=self.root)

    def open_storage(self) -> None:
        try:
            folder = data_dir()
            folder.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(folder))
            else:
                subprocess.Popen(["xdg-open", str(folder)], close_fds=True)
        except Exception as exc:
            messagebox.showerror(
                "Folder penyimpanan tidak dapat dibuka",
                str(exc),
                parent=self.root,
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zybtool-gui")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Periksa dependensi UI dan pengaturan tanpa membuka jendela.",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        import tkinter

        status = settings_status()
        print(f"Tkinter: {tkinter.TkVersion}")
        print(f"Settings storage: {status['storage']}")
        print(f"Decoder key configured: {status['decoder_key_configured']}")
        print(f"Allow-list configured: {status['allowlist_configured']}")
        return 0

    root = tk.Tk()
    ZYBToolApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
