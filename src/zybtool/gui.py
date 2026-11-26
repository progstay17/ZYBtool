"""Tkinter desktop shell and Security & Keys settings for ZYB Tool."""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import tkinter as tk
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from zybtool import __version__
from zybtool.settings import (
    data_dir,
    decoder_public_key_hex,
    export_decoder_private_key,
    generate_decoder_keypair,
    remove_decoder_private_key,
    set_decoder_private_key,
    settings_status,
)
from zybtool.workspace import WorkspaceMixin

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


class ZYBToolApp(WorkspaceMixin):
    """ZYBTool desktop shell with functional verification and reporting workspace."""

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
        self.storage_var = tk.StringVar(value=str(data_dir()))
        self.generate_button: tk.Button | None = None
        self.import_button: tk.Button | None = None
        self.copy_button: tk.Button | None = None
        self.remove_button: tk.Button | None = None
        self.export_button: tk.Button | None = None
        self.public_entry: tk.Entry | None = None
        self._init_workspace()
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
            "Overview",
            "QR Decoder",
            "Verify Recordings",
            "Review Queue",
            "Arrange Folder",
            "Output & Reports",
            "Activity Log",
            "Preferences",
            "Settings",
        ]
        for label in nav_items:
            button = tk.Button(
                sidebar,
                text=f"   {label}",
                anchor="w",
                relief="flat",
                bd=0,
                padx=12,
                pady=11,
                bg=SIDEBAR,
                fg=SECONDARY,
                activebackground=SURFACE_HOVER,
                activeforeground=TEXT,
                font=(FONT, 10),
                cursor="hand2",
                command=partial(self.show_page, label),
            )
            button.pack(fill="x", padx=12, pady=1)
            self.nav_buttons[label] = button

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
        tk.Label(topbar, text="ZYB TOOL  /  LOCAL WORKSPACE", bg=BG, fg=MUTED, font=(MONO, 9)).pack(
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

        self.show_page("Overview")

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
        tk.Label(header, text="Decoder Settings", bg=BG, fg=TEXT, font=(FONT, 25, "bold")).pack(
            anchor="w"
        )
        tk.Label(
            header,
            text="Satu public key untuk AITQR. Tidak ada pairing atau allow-list.",
            bg=BG,
            fg=SECONDARY,
            font=(FONT, 10),
        ).pack(anchor="w", pady=(6, 0))

        key_card = self._card(page)
        key_card.grid(row=1, column=0, sticky="ew", padx=34, pady=(0, 14))
        self._card_title(
            key_card,
            "Encrypted QR decoder",
            "X25519 ? Metaqr MQ1 ? private key dilindungi Windows DPAPI",
        )
        state = tk.Frame(key_card, bg=SURFACE)
        state.pack(fill="x", pady=(16, 12))
        tk.Label(
            state, textvariable=self.key_state_var, bg=SURFACE, fg=GREEN, font=(FONT, 11, "bold")
        ).pack(anchor="w")
        tk.Label(
            state,
            textvariable=self.key_detail_var,
            bg=SURFACE,
            fg=SECONDARY,
            font=(FONT, 9),
            justify="left",
            wraplength=820,
        ).pack(anchor="w", pady=(4, 0))
        tk.Label(
            key_card,
            text="PUBLIC KEY ? TEMPEL KE PENGATURAN AITQR",
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

        actions = tk.Frame(key_card, bg=SURFACE)
        actions.pack(fill="x", pady=(16, 0))
        self.generate_button = self._button(
            actions, "Generate key", self.generate_key, primary=True
        )
        self.generate_button.pack(side="left")
        self.import_button = self._button(
            actions, "Import private key", self.import_private_key, primary=False
        )
        self.import_button.pack(side="left", padx=(8, 0))
        self.export_button = self._button(
            actions, "Export private key", self.export_private_key, danger=True
        )
        self.export_button.pack(side="left", padx=(8, 0))
        self.remove_button = self._button(actions, "Remove key", self.remove_key, danger=True)
        self.remove_button.pack(side="left", padx=(8, 0))

        handoff = self._card(page)
        handoff.grid(row=2, column=0, sticky="ew", padx=34, pady=(0, 14))
        self._card_title(handoff, "Simple key handoff", "Hanya satu kali setup")
        tk.Label(
            handoff,
            text="1. Generate atau import private key di ZYBTool.   2. Copy public key.   3. Tempel ke AITQR.   4. AITQR membuat QR terenkripsi MQ1; ZYBTool membacanya dengan private key ini.",
            bg=SURFACE,
            fg=TEXT,
            font=(FONT, 9),
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(14, 0))
        tk.Label(
            handoff,
            text="MQ1 digunakan untuk mengenkripsi isi QR. ZYBTool mendekripsi dengan private key lokal dan memvalidasi envelope payload.",
            bg=SURFACE,
            fg=AMBER,
            font=(FONT, 9),
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(10, 0))

        storage = self._card(page)
        storage.grid(row=3, column=0, sticky="ew", padx=34, pady=(0, 28))
        self._card_title(storage, "Local security storage", "Windows DPAPI ? current Windows user")
        row = tk.Frame(storage, bg=SURFACE)
        row.pack(fill="x", pady=(14, 0))
        tk.Label(
            row,
            textvariable=self.storage_var,
            bg=SURFACE,
            fg=TEXT,
            font=(MONO, 9),
            wraplength=760,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        self._button(row, "Open folder", self.open_storage, primary=False).pack(
            side="right", padx=(12, 0)
        )

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

            if self.export_button is not None:
                self.export_button.configure(
                    state="normal" if status["decoder_key_configured"] else "disabled"
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
            self._log_activity("Decoder key generated")
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
            self._log_activity("Decoder private key imported")
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

    def export_private_key(self) -> None:
        if not self.public_key_var.get():
            return
        confirmed = messagebox.askyesno(
            "Export private key",
            "File hasil export berisi private key plaintext. Siapa pun yang memilikinya dapat mendekripsi QR untuk public key ini. Simpan di media terenkripsi dan jangan kirim melalui chat/email. Lanjutkan?",
            icon="warning",
            parent=self.root,
        )
        if not confirmed:
            return
        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export private decoder key",
            defaultextension=".key",
            filetypes=[
                ("ZYBTool private key", "*.key"),
                ("Text file", "*.txt"),
                ("All files", "*.*"),
            ],
            initialfile="ZYBTool-decoder-private.key",
        )
        if not selected:
            return
        try:
            destination = export_decoder_private_key(Path(selected))
            self._log_activity("Decoder private key exported", "WARNING")
            self._set_status("Private key berhasil diekspor. Simpan file secara aman.")
            messagebox.showwarning(
                "Private key diekspor",
                "Private key plaintext disimpan di "
                + str(destination)
                + ". Simpan file di media terenkripsi; jangan upload ke GitHub atau kirim melalui chat/email.",
                parent=self.root,
            )
        except Exception as exc:
            messagebox.showerror("Export private key gagal", str(exc), parent=self.root)
            self._set_status(f"Export private key gagal: {exc}", error=True)

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
            self._log_activity("Decoder key removed", "WARNING")
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
        return 0

    root = tk.Tk()
    ZYBToolApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
