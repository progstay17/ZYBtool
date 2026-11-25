"""Functional workspace pages for the ZYBTool desktop application."""

from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
import webbrowser
from datetime import UTC
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from zybtool.models import ResultStatus
from zybtool.naming import (
    DEFAULT_CONFIG,
    DEFAULT_FIELD_MAP,
    DEFAULT_TEMPLATE,
    TOKENS,
    preview_folder_name,
    scan_json_file,
    validate_template,
)
from zybtool.operations import execute_move_plan, export_excel, undo_move
from zybtool.output import create_output_plan
from zybtool.pipeline import run_verification, write_report
from zybtool.settings import data_dir

PREFERENCE_DEFAULTS: dict[str, Any] = {
    "source_root": "",
    "report_root": str(Path.home() / "ZYB_Reports"),
    "excel_root": str(Path.home() / "ZYB_Excel"),
    "organized_root": str(Path.home() / "ZYB_Organized"),
    "naming": dict(DEFAULT_CONFIG),
}


def load_preferences() -> dict[str, Any]:
    path = data_dir() / "preferences.json"
    values = dict(PREFERENCE_DEFAULTS)
    values["naming"] = {**DEFAULT_CONFIG, "field_map": dict(DEFAULT_FIELD_MAP)}
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("preferences.json harus berupa object JSON.")
        for key in ("source_root", "report_root", "excel_root", "organized_root"):
            if isinstance(loaded.get(key), str):
                values[key] = loaded[key].strip()
        naming = loaded.get("naming")
        if isinstance(naming, dict):
            stored_map = (
                naming.get("field_map") if isinstance(naming.get("field_map"), dict) else {}
            )
            values["naming"] = {
                **values["naming"],
                "source_json": str(naming.get("source_json") or "").strip(),
                "template": str(naming.get("template") or DEFAULT_TEMPLATE),
                "field_map": {
                    token: str(stored_map.get(token) or DEFAULT_FIELD_MAP[token])
                    for token in TOKENS
                },
                "no_shift": bool(naming.get("no_shift", False)),
            }
    return values


def save_preferences(values: dict[str, Any]) -> None:
    path = data_dir() / "preferences.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    clean: dict[str, Any] = {}
    for key in ("source_root", "report_root", "excel_root", "organized_root"):
        raw = str(values.get(key, "") or "").strip()
        clean[key] = str(Path(raw).expanduser().resolve()) if raw else ""
    naming = values.get("naming") if isinstance(values.get("naming"), dict) else {}
    template = validate_template(str(naming.get("template") or DEFAULT_TEMPLATE))
    field_map = naming.get("field_map") if isinstance(naming.get("field_map"), dict) else {}
    clean["naming"] = {
        "source_json": str(naming.get("source_json") or "").strip(),
        "template": template,
        "field_map": {
            token: str(field_map.get(token) or DEFAULT_FIELD_MAP[token]) for token in TOKENS
        },
        "no_shift": bool(naming.get("no_shift", False)),
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


BG = "#080D0B"
SIDEBAR = "#0E1511"
SURFACE = "#131D17"
HOVER = "#19251D"
LINE = "#26372C"
TEXT = "#E8F0E9"
SECONDARY = "#A0B0A4"
MUTED = "#718176"
GREEN = "#A3F36B"
AMBER = "#F2B84B"
RED = "#FF6B68"
FONT = "Segoe UI"
MONO = "Consolas"


class WorkspaceMixin:
    """Overview, verification, review, reports and activity pages."""

    root: tk.Tk
    content: tk.Frame
    nav_buttons: dict[str, tk.Button]

    def _button(
        self,
        parent: tk.Widget,
        label: str,
        command: Any,
        *,
        primary: bool = False,
        danger: bool = False,
    ) -> tk.Button:
        raise NotImplementedError

    def _set_status(self, message: str, *, error: bool = False) -> None:
        raise NotImplementedError

    def _build_settings_content(self) -> None:
        raise NotImplementedError

    def _init_workspace(self) -> None:
        self.current_report: Any = None
        self.report_directory: Path | None = None
        self.preferences = load_preferences()
        self.naming_preferences = dict(self.preferences.get("naming") or DEFAULT_CONFIG)
        self.source_path = tk.StringVar(value=self.preferences["source_root"])
        self.report_path = tk.StringVar(value=self.preferences["report_root"])
        self.excel_path = tk.StringVar(value=self.preferences["excel_root"])
        self.output_path = tk.StringVar(value=self.preferences["organized_root"])
        self.output_queue: queue.Queue[Any] = queue.Queue()
        self.output_running = False
        self.last_move_path: Path | None = None
        self.job_queue: queue.Queue[Any] = queue.Queue()
        self.job_running = False
        self.activity_entries: list[dict[str, str]] = []
        self.nav_buttons: dict[str, tk.Button] = {}
        self.current_page = "Overview"
        self._load_activity()

    def _load_activity(self) -> None:
        try:
            path = data_dir() / "activity.jsonl"
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines()[-300:]:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        self.activity_entries.append(item)
        except (OSError, ValueError):
            self.activity_entries = []

    def _log_activity(self, message: str, severity: str = "INFO") -> None:
        from datetime import datetime

        item = {
            "time": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
            "severity": severity,
            "message": message,
        }
        self.activity_entries.append(item)
        self.activity_entries = self.activity_entries[-500:]
        try:
            folder = data_dir()
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / "activity.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def show_page(self, name: str) -> None:
        if self.job_running and name == "Verify Recordings":
            pass
        self.current_page = name
        for label, button in self.nav_buttons.items():
            selected = label == name
            button.configure(
                bg=HOVER if selected else SIDEBAR,
                fg=GREEN if selected else SECONDARY,
                font=(FONT, 10, "bold" if selected else "normal"),
            )
        for child in self.content.winfo_children():
            child.destroy()
        builders = {
            "Overview": self._page_overview,
            "Verify Recordings": self._page_verify,
            "Review Queue": self._page_review,
            "Arrange Folder": self._page_arrange,
            "Output & Reports": self._page_reports,
            "Activity Log": self._page_activity,
            "Preferences": self._page_preferences,
            "Settings": self._build_settings_content,
        }
        builders[name]()

    def _header(
        self, title: str, subtitle: str, action: str | None = None, callback: Any = None
    ) -> None:
        header = tk.Frame(self.content, bg=BG)
        header.pack(fill="x", padx=34, pady=(28, 22))
        left = tk.Frame(header, bg=BG)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=title, bg=BG, fg=TEXT, font=(FONT, 25, "bold")).pack(anchor="w")
        tk.Label(left, text=subtitle, bg=BG, fg=SECONDARY, font=(FONT, 10)).pack(
            anchor="w", pady=(6, 0)
        )
        if action and callback:
            self._button(header, action, callback, primary=True).pack(side="right", padx=(12, 0))

    def _panel(self, title: str, subtitle: str = "") -> tk.Frame:
        panel = tk.Frame(
            self.content,
            bg=SURFACE,
            padx=18,
            pady=16,
            highlightthickness=1,
            highlightbackground=LINE,
        )
        tk.Label(panel, text=title, bg=SURFACE, fg=TEXT, font=(FONT, 12, "bold")).pack(anchor="w")
        if subtitle:
            tk.Label(panel, text=subtitle, bg=SURFACE, fg=MUTED, font=(FONT, 9)).pack(
                anchor="w", pady=(4, 0)
            )
        return panel

    def _tree(
        self, parent: tk.Widget, columns: tuple[str, ...], headings: tuple[str, ...]
    ) -> ttk.Treeview:
        style = ttk.Style(self.root)
        style.configure(
            "ZYB.Treeview",
            background=SURFACE,
            fieldbackground=SURFACE,
            foreground=TEXT,
            rowheight=30,
            borderwidth=0,
        )
        style.configure(
            "ZYB.Treeview.Heading",
            background=HOVER,
            foreground=SECONDARY,
            relief="flat",
            font=(FONT, 9, "bold"),
        )
        style.map(
            "ZYB.Treeview", background=[("selected", "#29402D")], foreground=[("selected", TEXT)]
        )
        tree = ttk.Treeview(parent, columns=columns, show="headings", style="ZYB.Treeview")
        for col, heading in zip(columns, headings, strict=False):
            tree.heading(col, text=heading)
            tree.column(col, width=130, minwidth=85, anchor="w")
        tree.pack(fill="both", expand=True, pady=(12, 0))
        return tree

    def _page_overview(self) -> None:
        self._header(
            "Overview",
            "Ringkasan pekerjaan verifikasi lokal.",
            "New verification",
            lambda: self.show_page("Verify Recordings"),
        )
        report = self.current_report
        counts = {status: 0 for status in ResultStatus}
        if report:
            for item in report.recordings:
                counts[item.status] += 1
        metrics = tk.Frame(self.content, bg=BG)
        metrics.pack(fill="x", padx=34)
        values = [
            ("FOLDERS DISCOVERED", str(len(report.units)) if report else "—"),
            ("RECORDINGS", str(len(report.recordings)) if report else "—"),
            ("QR DECRYPTED", str(counts[ResultStatus.QR_DECRYPTED]) if report else "?"),
            (
                "NEEDS ATTENTION",
                str(
                    sum(
                        counts[s]
                        for s in (
                            ResultStatus.AMBIGUOUS,
                            ResultStatus.INCOMPLETE,
                            ResultStatus.METADATA_MISMATCH,
                            ResultStatus.QR_DECRYPT_FAILED,
                            ResultStatus.CORRUPTED,
                            ResultStatus.QR_MISSING,
                            ResultStatus.QR_DECRYPT_FAILED,
                        )
                    )
                )
                if report
                else "—",
            ),
        ]
        for label, value in values:
            card = tk.Frame(
                metrics,
                bg=SURFACE,
                padx=18,
                pady=16,
                highlightthickness=1,
                highlightbackground=LINE,
            )
            card.pack(side="left", fill="both", expand=True, padx=(0, 10))
            tk.Label(card, text=label, bg=SURFACE, fg=MUTED, font=(FONT, 8, "bold")).pack(
                anchor="w"
            )
            tk.Label(
                card,
                text=value,
                bg=SURFACE,
                fg=GREEN if label == "QR DECRYPTED" and report else TEXT,
                font=(MONO, 24, "bold"),
            ).pack(anchor="w", pady=(8, 0))
        panel = self._panel(
            "Latest verification", "Data berasal dari pemindaian terakhir; tidak ada metrik contoh."
        )
        panel.pack(fill="both", expand=True, padx=34, pady=18)
        if report:
            tk.Label(
                panel,
                text=f"Source: {report.source_root}",
                bg=SURFACE,
                fg=TEXT,
                font=(MONO, 9),
                wraplength=850,
                justify="left",
            ).pack(anchor="w", pady=(16, 6))
            tk.Label(
                panel,
                text=f"Run ID: {report.run_id}    ·    {len(report.recordings)} recording    ·    {len(report.findings)} temuan",
                bg=SURFACE,
                fg=SECONDARY,
                font=(FONT, 9),
            ).pack(anchor="w")
            self._button(
                panel, "Open report details", lambda: self.show_page("Output & Reports")
            ).pack(anchor="w", pady=(14, 0))
        else:
            tk.Label(
                panel,
                text="Belum ada hasil verifikasi.",
                bg=SURFACE,
                fg=TEXT,
                font=(FONT, 12, "bold"),
            ).pack(anchor="w", pady=(18, 4))
            tk.Label(
                panel,
                text="Pilih folder recording pada Verify Recordings untuk memulai. Folder sumber hanya dibaca dan tidak akan diubah.",
                bg=SURFACE,
                fg=SECONDARY,
                font=(FONT, 9),
                wraplength=800,
            ).pack(anchor="w")
            self._button(
                panel,
                "Select recording folder",
                lambda: self.show_page("Verify Recordings"),
                primary=True,
            ).pack(anchor="w", pady=(16, 0))

    def _page_verify(self) -> None:
        self._header(
            "Verify Recordings",
            "Pindai folder lokal secara read-only, lalu tinjau bukti dan hasilnya.",
        )
        panel = self._panel(
            "1. Source folder", "Folder sumber tidak pernah dipindahkan, diubah, atau dihapus."
        )
        panel.pack(fill="x", padx=34, pady=(0, 14))
        row = tk.Frame(panel, bg=SURFACE)
        row.pack(fill="x", pady=(14, 0))
        entry = tk.Entry(
            row,
            textvariable=self.source_path,
            bg="#0A100D",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=(MONO, 9),
        )
        entry.pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 8))
        self._button(row, "Browse", self._choose_source).pack(side="right")
        out = self._panel(
            "2. Report destination",
            "Artefak JSON, CSV, HTML dan inventory disimpan terpisah dari folder sumber.",
        )
        out.pack(fill="x", padx=34, pady=(0, 14))
        row2 = tk.Frame(out, bg=SURFACE)
        row2.pack(fill="x", pady=(14, 0))
        tk.Entry(
            row2,
            textvariable=self.report_path,
            bg="#0A100D",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=(MONO, 9),
        ).pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 8))
        self._button(row2, "Browse", self._choose_report_dir).pack(side="right")
        run = self._panel(
            "3. Verification",
            "Discovery · metadata · video timeline · QR/MQ1 (selalu discan; dekripsi jika private key tersedia) · grouping · reports",
        )
        run.pack(fill="x", padx=34, pady=(0, 24))
        self.verify_status = tk.StringVar(
            value="Siap. QR terenkripsi MQ1 dipindai; private key hanya diperlukan untuk dekripsi."
        )
        tk.Label(
            run,
            textvariable=self.verify_status,
            bg=SURFACE,
            fg=SECONDARY,
            font=(FONT, 9),
            wraplength=850,
        ).pack(anchor="w", pady=(14, 10))
        self.verify_progress = ttk.Progressbar(run, mode="indeterminate", length=360)
        self.verify_progress.pack(anchor="w")
        self.verify_button = self._button(
            run, "Start verification", self._start_verification, primary=True
        )
        self.verify_button.pack(anchor="w", pady=(14, 0))
        if self.job_running:
            self.verify_button.configure(state="disabled")
            self.verify_progress.start(12)

    def _choose_source(self) -> None:
        selected = filedialog.askdirectory(parent=self.root, title="Pilih folder recording")
        if selected:
            self.source_path.set(selected)

    def _choose_report_dir(self) -> None:
        selected = filedialog.askdirectory(parent=self.root, title="Pilih folder laporan")
        if selected:
            self.report_path.set(selected)

    def _start_verification(self) -> None:
        if self.job_running:
            return
        source = self.source_path.get().strip()
        output = self.report_path.get().strip()
        if not source or not Path(source).is_dir():
            messagebox.showwarning(
                "Folder sumber belum valid",
                "Pilih folder recording yang tersedia.",
                parent=self.root,
            )
            return
        if not output:
            messagebox.showwarning(
                "Folder laporan belum ditentukan", "Pilih folder tujuan laporan.", parent=self.root
            )
            return
        if Path(source).resolve() == Path(output).expanduser().resolve():
            messagebox.showwarning(
                "Tujuan tidak aman",
                "Folder laporan harus terpisah dari folder sumber.",
                parent=self.root,
            )
            return
        self.preferences["source_root"] = source
        self.source_path.set(source)
        save_preferences(self.preferences)
        self._log_activity(f"Verification started: {source}")
        self._set_status("Verifikasi berjalan. Folder sumber tetap read-only.")
        if hasattr(self, "verify_button"):
            self.verify_button.configure(state="disabled")
            self.verify_progress.start(12)
            self.verify_status.set(
                "Memindai metadata dan video. Waktu proses bergantung pada ukuran file."
            )

        def worker() -> None:
            try:
                report = run_verification(Path(source))
                destination = write_report(report, Path(output))
                self.job_queue.put(("success", report, destination))
            except Exception as exc:
                self.job_queue.put(("error", str(exc), None))

        threading.Thread(target=worker, name="zyb-verification", daemon=True).start()
        self.root.after(150, self._poll_verification)

    def _poll_verification(self) -> None:
        try:
            kind, value, destination = self.job_queue.get_nowait()
        except queue.Empty:
            self.root.after(150, self._poll_verification)
            return
        self.job_running = False
        if hasattr(self, "verify_progress"):
            self.verify_progress.stop()
        if kind == "success":
            self.current_report = value
            self.report_directory = destination
            self._log_activity(f"Verification completed: {value.run_id}")
            self._set_status(f"Verifikasi selesai: {len(value.recordings)} recording ditemukan.")
            if hasattr(self, "verify_status"):
                self.verify_status.set(
                    f"Selesai. {len(value.recordings)} recording · {len(value.findings)} temuan. Laporan: {destination}"
                )
                self.verify_button.configure(state="normal")
            messagebox.showinfo(
                "Verifikasi selesai",
                f"Recording: {len(value.recordings)}\nTemuan: {len(value.findings)}\n\nLaporan:\n{destination}",
                parent=self.root,
            )
            self.show_page("Output & Reports")
        else:
            self._log_activity(f"Verification failed: {value}", "ERROR")
            self._set_status(f"Verifikasi gagal: {value}", error=True)
            messagebox.showerror("Verifikasi gagal", str(value), parent=self.root)
            if self.current_page == "Verify Recordings" and hasattr(self, "verify_button"):
                self.verify_button.configure(state="normal")
                self.verify_status.set("Gagal. Periksa pesan kesalahan dan coba kembali.")

    def _page_review(self) -> None:
        self._header(
            "Review Queue",
            "Temuan yang memerlukan perhatian operator. Tidak ada auto-fix atau keputusan otomatis.",
        )
        panel = self._panel(
            "Items requiring review",
            "Ambiguous, incomplete, mismatch, QR missing, dekripsi QR gagal, dan corruption.",
        )
        panel.pack(fill="both", expand=True, padx=34, pady=(0, 24))
        if not self.current_report:
            tk.Label(
                panel,
                text="Belum ada hasil untuk ditinjau. Jalankan verifikasi terlebih dahulu.",
                bg=SURFACE,
                fg=SECONDARY,
                font=(FONT, 10),
            ).pack(anchor="w", pady=(18, 0))
            self._button(
                panel,
                "Go to verification",
                lambda: self.show_page("Verify Recordings"),
                primary=True,
            ).pack(anchor="w", pady=(14, 0))
            return
        statuses = {
            ResultStatus.AMBIGUOUS,
            ResultStatus.INCOMPLETE,
            ResultStatus.METADATA_MISMATCH,
            ResultStatus.CORRUPTED,
            ResultStatus.QR_MISSING,
            ResultStatus.QR_DECRYPT_FAILED,
            ResultStatus.QR_DECRYPT_FAILED,
        }
        rows = [r for r in self.current_report.recordings if r.status in statuses]
        if not rows:
            tk.Label(
                panel,
                text="Tidak ada recording yang masuk antrean review pada hasil terakhir.",
                bg=SURFACE,
                fg=GREEN,
                font=(FONT, 10, "bold"),
            ).pack(anchor="w", pady=(18, 0))
            return
        tree = self._tree(
            panel,
            ("status", "device", "segments", "duration", "reason"),
            ("STATUS", "DEVICE", "SEGMENTS", "DURATION", "REASONS"),
        )
        for item in rows:
            tree.insert(
                "",
                "end",
                values=(
                    item.status.value,
                    item.device_id or "—",
                    len(item.segments),
                    "—" if item.actual_duration_s is None else f"{item.actual_duration_s:.2f}s",
                    "; ".join(item.reasons) or "Perlu pemeriksaan manual",
                ),
            )

    def _page_arrange(self) -> None:
        self._header(
            "Arrange Folder",
            "ZYWTool-style grouping with MOVE, SHA-256 verification, persistent destination and Undo.",
        )
        panel = self._panel(
            "Organized Folders",
            "Same group key goes into the same folder. Existing groups are reused; existing session folders are never overwritten.",
        )
        panel.pack(fill="x", padx=34, pady=(0, 14))
        row = tk.Frame(panel, bg=SURFACE)
        row.pack(fill="x", pady=(14, 0))
        tk.Entry(
            row,
            textvariable=self.output_path,
            bg="#0A100D",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=(MONO, 9),
        ).pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 8))
        self._button(row, "Browse", self._choose_output_dir).pack(side="right")
        tk.Label(
            panel,
            text="Format grup: YYYYMMDD_LOKASI_NamaRecorder_DEVICE_S<shift>_Aktivitas. Contoh: 20261117_MM12_RecorderA_ZY123_S2_Kitchen. Nama folder recording asli tetap dipertahankan di dalam grup.",
            bg=SURFACE,
            fg=SECONDARY,
            font=(FONT, 9),
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(12, 8))
        tk.Label(
            panel,
            text="QR belum didekripsi masuk _UNNAMED. Recording CORRUPTED masuk _REJECTED. Recording ambigu atau tidak lengkap tetap diblokir untuk review.",
            bg=SURFACE,
            fg=AMBER,
            font=(FONT, 9),
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))
        self.output_status = tk.StringVar(value="Siap menyiapkan Arrange Folder.")
        tk.Label(panel, textvariable=self.output_status, bg=SURFACE, fg=MUTED, font=(FONT, 9)).pack(
            anchor="w", pady=(0, 8)
        )
        self.output_progress = ttk.Progressbar(panel, mode="indeterminate", length=360)
        self.output_progress.pack(anchor="w")
        self.output_button = self._button(
            panel, "Preview Arrange & Execute MOVE", self._prepare_local_output, primary=True
        )
        self.output_button.pack(anchor="w", pady=(14, 0))
        self._button(panel, "Undo last MOVE", self._undo_last_move, danger=True).pack(
            anchor="w", pady=(8, 0)
        )
        if not self.current_report:
            self.output_button.configure(state="disabled")
            tk.Label(
                panel,
                text="Jalankan verification terlebih dahulu agar rencana Arrange dapat dibuat.",
                bg=SURFACE,
                fg=SECONDARY,
                font=(FONT, 9),
            ).pack(anchor="w", pady=(12, 0))
        if self.output_running:
            self.output_button.configure(state="disabled")
            self.output_progress.start(12)

    def _page_reports(self) -> None:
        self._header(
            "Output & Reports",
            "Laporan hasil verifikasi lokal. Tidak ada koneksi atau transfer OSS.",
        )
        panel = self._panel(
            "Latest report", "JSON kanonik · CSV untuk analisis · HTML untuk supervisor"
        )
        panel.pack(fill="both", expand=True, padx=34, pady=(0, 14))
        if not self.current_report:
            tk.Label(
                panel, text="Belum ada laporan.", bg=SURFACE, fg=SECONDARY, font=(FONT, 10)
            ).pack(anchor="w", pady=(18, 0))
            self._button(
                panel,
                "Start verification",
                lambda: self.show_page("Verify Recordings"),
                primary=True,
            ).pack(anchor="w", pady=(14, 0))
            return
        report = self.current_report
        tk.Label(
            panel, text=f"Run ID  {report.run_id}", bg=SURFACE, fg=GREEN, font=(MONO, 10, "bold")
        ).pack(anchor="w", pady=(16, 6))
        tk.Label(
            panel,
            text=f"Source  {report.source_root}",
            bg=SURFACE,
            fg=TEXT,
            font=(MONO, 9),
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=4)
        tk.Label(
            panel,
            text=f"Generated  {report.generated_at}",
            bg=SURFACE,
            fg=SECONDARY,
            font=(MONO, 9),
        ).pack(anchor="w", pady=4)
        tree = self._tree(
            panel,
            ("status", "device", "segments", "duration", "trust"),
            ("STATUS", "DEVICE", "SEGMENTS", "ACTUAL DURATION", "TRUST LEVEL"),
        )
        for item in report.recordings:
            tree.insert(
                "",
                "end",
                values=(
                    item.status.value,
                    item.device_id or "—",
                    len(item.segments),
                    "—" if item.actual_duration_s is None else f"{item.actual_duration_s:.2f}s",
                    item.trust_level,
                ),
            )
        actions = tk.Frame(panel, bg=SURFACE)
        actions.pack(fill="x", pady=(14, 0))
        self._button(actions, "Open report folder", self._open_report_folder).pack(side="left")
        self._button(actions, "Open supervisor HTML", self._open_html_report, primary=True).pack(
            side="left", padx=(8, 0)
        )
        self._button(actions, "Export Excel", self._export_excel, primary=True).pack(
            side="left", padx=(8, 0)
        )
        self._button(actions, "Copy report path", self._copy_report_path).pack(
            side="left", padx=(8, 0)
        )
        output_panel = self._panel(
            "Arrange Folder · MOVE",
            "Pindahkan recording ke folder tujuan, pertahankan struktur, verifikasi hash, dan sediakan Undo.",
        )
        output_panel.pack(fill="x", padx=34, pady=(0, 14))
        output_row = tk.Frame(output_panel, bg=SURFACE)
        output_row.pack(fill="x", pady=(14, 0))
        tk.Entry(
            output_row,
            textvariable=self.output_path,
            bg="#0A100D",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=(MONO, 9),
        ).pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 8))
        self._button(output_row, "Browse", self._choose_output_dir).pack(side="right")
        tk.Label(
            output_panel,
            text="METADATA_ONLY dipindahkan ke _UNNAMED untuk keputusan operator. Nama operasional dibuat dari QR MQ1 yang berhasil didekripsi dan lolos korelasi device ID. QR tidak mengautentikasi pembuatnya. Recording ambigu/tidak lengkap/bermasalah diblokir. Manifest hash lokal belum ditandatangani.",
            bg=SURFACE,
            fg=SECONDARY,
            font=(FONT, 9),
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(12, 8))
        self.output_status = tk.StringVar(value="Siap menyiapkan output lokal.")
        tk.Label(
            output_panel, textvariable=self.output_status, bg=SURFACE, fg=MUTED, font=(FONT, 9)
        ).pack(anchor="w", pady=(0, 8))
        self.output_progress = ttk.Progressbar(output_panel, mode="indeterminate", length=360)
        self.output_progress.pack(anchor="w")
        self.output_button = self._button(
            output_panel, "Preview & Move Recordings", self._prepare_local_output, primary=True
        )
        self.output_button.pack(anchor="w", pady=(14, 0))
        self._button(output_panel, "Undo last MOVE", self._undo_last_move, danger=True).pack(
            anchor="w", pady=(8, 0)
        )
        if self.output_running:
            self.output_button.configure(state="disabled")
            self.output_progress.start(12)

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(parent=self.root, title="Pilih folder output lokal")
        if selected:
            self.output_path.set(selected)

    def _prepare_local_output(self) -> None:
        if self.output_running:
            return
        if not self.current_report:
            return
        destination = self.output_path.get().strip()
        if not destination:
            messagebox.showwarning(
                "Folder output belum ditentukan", "Pilih folder output lokal.", parent=self.root
            )
            return
        try:
            plan = create_output_plan(
                self.current_report, Path(destination), self.naming_preferences
            )
        except Exception as exc:
            messagebox.showerror("Output plan gagal", str(exc), parent=self.root)
            return
        if not plan.items:
            details = "\n".join(plan.blocked[:12]) or "Tidak ada recording yang memenuhi syarat."
            messagebox.showwarning("Tidak ada output yang aman", details, parent=self.root)
            return
        unnamed = sum(item.folder_name.startswith("_UNNAMED/") for item in plan.items)
        rejected = sum(item.folder_name == "_REJECTED" for item in plan.items)
        group_names = sorted({item.folder_name for item in plan.items}, key=str.casefold)
        folder_preview = "\n".join(f"  • {name}" for name in group_names[:10])
        if len(group_names) > 10:
            folder_preview += f"\n  … dan {len(group_names) - 10} grup lainnya"
        preview = (
            f"Siap DIPINDAHKAN: {len(plan.items)} recording ke {len(group_names)} folder grup\n"
            f"Dengan nama operasional dari QR: {len(plan.items) - unnamed}\n"
            f"Masuk _UNNAMED: {unnamed}\n"
            f"Masuk _REJECTED: {rejected}\n"
            f"Diblokir: {len(plan.blocked)}\n\n"
            f"Preview folder grup:\n{folder_preview}\n\n"
            f"Tujuan: {plan.destination}\n\n"
            "Recording akan dipindahkan dari sumber. Folder grup yang sudah ada akan dipakai kembali. "
            "Folder sesi yang bentrok tidak akan ditimpa; jurnal Undo per proses akan dibuat. Lanjutkan MOVE?"
        )
        if plan.blocked:
            preview += "\n\nSebagian recording diblokir karena bukti belum cukup; lihat detail pada Review Queue."
        if not messagebox.askyesno(
            "Konfirmasi MOVE recording", preview, icon="warning", parent=self.root
        ):
            return
        self.output_running = True
        self.output_button.configure(state="disabled")
        self.output_progress.start(12)
        self.output_status.set(
            "Memindahkan folder dan memeriksa struktur/hash. Jangan tutup aplikasi."
        )
        self._log_activity(f"Arrange MOVE started: {plan.destination}")

        def worker() -> None:
            try:
                result = execute_move_plan(plan, confirmed=True)
                self.output_queue.put(("success", result))
            except Exception as exc:
                self.output_queue.put(("error", str(exc)))

        threading.Thread(target=worker, name="zyb-output-move", daemon=True).start()
        self.root.after(150, self._poll_output_copy)

    def _poll_output_copy(self) -> None:
        try:
            kind, value = self.output_queue.get_nowait()
        except queue.Empty:
            self.root.after(150, self._poll_output_copy)
            return
        self.output_running = False
        if hasattr(self, "output_progress"):
            self.output_progress.stop()
        if kind == "success":
            self.last_move_path = Path(value)
            self._log_activity(f"Arrange MOVE completed: {value}")
            self._set_status("Arrange MOVE selesai dan hash cocok. Undo tersedia.")
            if hasattr(self, "output_status"):
                self.output_status.set(f"Selesai. Output: {value}")
                self.output_button.configure(state="normal")
            messagebox.showinfo(
                "Output lokal selesai",
                f"Pemindahan dan pemeriksaan SHA-256 selesai.\n\n{value}\n\nManifest berisi hash file dan belum ditandatangani.",
                parent=self.root,
            )
        else:
            self._log_activity(f"Arrange MOVE failed: {value}", "ERROR")
            self._set_status(f"Output lokal gagal: {value}", error=True)
            if hasattr(self, "output_status"):
                self.output_status.set(f"Gagal: {value}")
                self.output_button.configure(state="normal")
            messagebox.showerror("Output lokal gagal", str(value), parent=self.root)

    def _export_excel(self) -> None:
        if not self.current_report:
            return
        excel_root = self.excel_path.get().strip()
        if not excel_root:
            messagebox.showwarning(
                "Excel output belum diatur",
                "Atur folder Excel output di Preferences terlebih dahulu.",
                parent=self.root,
            )
            self.show_page("Preferences")
            return
        destination = Path(excel_root).expanduser() / "ZYB_Rekap.xlsx"
        try:
            result = export_excel(self.current_report, destination)
        except Exception as exc:
            messagebox.showerror("Excel export gagal", str(exc), parent=self.root)
            self._log_activity(f"Excel export failed: {exc}", "ERROR")
            return
        self._log_activity(f"Excel export completed: {result}")
        self._set_status("Excel berhasil diekspor.")
        messagebox.showinfo(
            "Excel selesai",
            f"Workbook berhasil dibuat/diperbarui:\n\n{result}\n\nSheet: ZY White, Cek File, Scan Audit, Rekonsiliasi. Kolom QC manual dipertahankan.",
            parent=self.root,
        )

    def _undo_last_move(self) -> None:
        candidate = getattr(self, "last_move_path", None)
        if candidate is None:
            selected = filedialog.askdirectory(
                parent=self.root, title="Pilih folder hasil MOVE untuk Undo"
            )
            if not selected:
                return
            candidate = Path(selected)
        if not messagebox.askyesno(
            "Konfirmasi Undo MOVE",
            f"Pindahkan kembali recording ke lokasi sumber asal?\n\n{candidate}\n\nUndo dibatalkan jika lokasi sumber sudah terisi atau tujuan berubah.",
            icon="warning",
            parent=self.root,
        ):
            return
        try:
            count = undo_move(candidate)
        except Exception as exc:
            messagebox.showerror("Undo MOVE gagal", str(exc), parent=self.root)
            self._log_activity(f"Undo MOVE failed: {exc}", "ERROR")
            return
        self._log_activity(f"Undo MOVE completed: {count} recording from {candidate}")
        self._set_status(f"Undo selesai: {count} recording dikembalikan.")
        self.last_move_path = None
        messagebox.showinfo(
            "Undo selesai",
            f"{count} folder recording dikembalikan ke lokasi asal.",
            parent=self.root,
        )

    def _open_report_folder(self) -> None:
        if self.report_directory and self.report_directory.exists():
            import os

            os.startfile(str(self.report_directory))
        else:
            messagebox.showinfo("Report folder", "Folder laporan belum tersedia.", parent=self.root)

    def _open_html_report(self) -> None:
        if self.report_directory:
            path = self.report_directory / "report.html"
            if path.exists():
                webbrowser.open(path.as_uri())

    def _copy_report_path(self) -> None:
        if self.report_directory:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(self.report_directory))
            self._set_status("Path laporan disalin.")

    def _page_preferences(self) -> None:
        self._header(
            "Preferences",
            "Atur lokasi workspace dan format nama folder operasional. Scan variabel tersedia khusus di halaman ini.",
        )
        panel = self._panel(
            "Workspace folders",
            "Folder tersimpan lokal pada profil Windows. Excel dibuat otomatis sebagai ZYB_Rekap.xlsx.",
        )
        panel.pack(fill="x", padx=34, pady=(0, 14))
        fields = (
            ("source_root", "Default source folder", "Folder recording sumber"),
            ("report_root", "Report output folder", "JSON, CSV, HTML dan inventory"),
            ("excel_root", "Excel output folder", "Workbook otomatis: ZYB_Rekap.xlsx"),
            ("organized_root", "Organized folders", "Tujuan Arrange Folder; MOVE, bukan copy"),
        )
        self.preference_vars = {}
        for key, label, hint in fields:
            row = tk.Frame(panel, bg=SURFACE)
            row.pack(fill="x", pady=(14, 0))
            tk.Label(
                row,
                text=label,
                bg=SURFACE,
                fg=TEXT,
                font=(FONT, 9, "bold"),
                width=22,
                anchor="w",
            ).pack(side="left")
            variable = tk.StringVar(value=self.preferences.get(key, ""))
            self.preference_vars[key] = variable
            tk.Entry(
                row,
                textvariable=variable,
                bg="#0A100D",
                fg=TEXT,
                insertbackground=TEXT,
                relief="flat",
                font=(MONO, 9),
            ).pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 8))
            self._button(
                row, "Browse", lambda v=variable, h=hint: self._browse_preference(v, h)
            ).pack(side="right")
            tk.Label(panel, text=hint, bg=SURFACE, fg=MUTED, font=(FONT, 8)).pack(
                anchor="w", pady=(3, 0)
            )

        naming = self.naming_preferences
        naming_panel = self._panel(
            "Naming Convention",
            "Scan JSON contoh untuk menemukan field. Mapping ini hanya mengatur nama folder output; metadata QR tetap harus lolos verifikasi.",
        )
        naming_panel.pack(fill="x", padx=34, pady=(0, 14))
        tk.Label(
            naming_panel, text="JSON VARIABLE SCANNER", bg=SURFACE, fg=GREEN, font=(FONT, 9, "bold")
        ).pack(anchor="w", pady=(12, 5))
        source_row = tk.Frame(naming_panel, bg=SURFACE)
        source_row.pack(fill="x")
        source_json_var = tk.StringVar(value=str(naming.get("source_json") or ""))
        tk.Entry(
            source_row,
            textvariable=source_json_var,
            bg="#0A100D",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=(MONO, 9),
        ).pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 8))

        def browse_json_sample() -> None:
            selected = filedialog.askopenfilename(
                parent=self.root,
                title="Pilih JSON contoh",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if selected:
                source_json_var.set(str(Path(selected).resolve()))

        self._button(source_row, "Browse JSON", browse_json_sample).pack(side="right", padx=(0, 8))
        detected_fields: list[dict[str, Any]] = []
        sample_data: Any = None
        fields_tree = ttk.Treeview(
            naming_panel, columns=("type", "sample"), show="tree headings", height=5
        )
        fields_tree.heading("#0", text="JSON FIELD PATH")
        fields_tree.heading("type", text="TYPE")
        fields_tree.heading("sample", text="SAMPLE VALUE")
        fields_tree.column("#0", width=260, minwidth=150)
        fields_tree.column("type", width=90, stretch=False)
        fields_tree.column("sample", width=480)
        fields_tree.pack(fill="both", expand=True, pady=(10, 4))
        scan_status = tk.StringVar(value="Belum ada file JSON yang dipindai.")
        tk.Label(naming_panel, textvariable=scan_status, bg=SURFACE, fg=MUTED, font=(FONT, 8)).pack(
            anchor="w", pady=(0, 8)
        )
        mapping_title = tk.Label(
            naming_panel, text="VARIABLE MAPPING", bg=SURFACE, fg=GREEN, font=(FONT, 9, "bold")
        )
        mapping_title.pack(anchor="w", pady=(8, 5))
        tk.Label(
            naming_panel,
            text="Default mengambil b, r, dn, sh, a dari payload QR terverifikasi; DATE berasal dari capture_date kamera. Field JSON yang dipilih dapat mengambil nilai dari session.json atau payload QR.",
            bg=SURFACE,
            fg=SECONDARY,
            font=(FONT, 8),
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        map_vars: dict[str, tk.StringVar] = {}
        map_boxes: dict[str, ttk.Combobox] = {}
        saved_map = naming.get("field_map") if isinstance(naming.get("field_map"), dict) else {}
        auto_label = "(Auto / default)"
        map_wrap = tk.Frame(naming_panel, bg=SURFACE)
        map_wrap.pack(fill="x")
        labels = (
            ("DATE", "Tanggal"),
            ("LOCATION_CODE", "Kode lokasi"),
            ("PERSON_NAME", "Nama recorder"),
            ("DEVICE_ID", "Device ID"),
            ("SESSION", "Shift / session"),
            ("ACTIVITY", "Aktivitas"),
        )
        for token, label in labels:
            row = tk.Frame(map_wrap, bg=SURFACE)
            row.pack(fill="x", pady=2)
            tk.Label(
                row, text=label, bg=SURFACE, fg=TEXT, width=22, anchor="w", font=(FONT, 9)
            ).pack(side="left")
            current = str(saved_map.get(token) or DEFAULT_FIELD_MAP[token])
            variable = tk.StringVar(value=current if current else auto_label)
            map_vars[token] = variable
            box = ttk.Combobox(
                row,
                textvariable=variable,
                values=[auto_label, *[v for v in DEFAULT_FIELD_MAP.values() if v]],
                state="readonly",
                width=52,
            )
            box.pack(side="left", fill="x", expand=True)
            map_boxes[token] = box

        def refresh_field_choices() -> None:
            paths = [item["path"] for item in detected_fields]
            defaults = [value for value in DEFAULT_FIELD_MAP.values() if value]
            choices = [auto_label, *dict.fromkeys([*defaults, *paths])]
            for box in map_boxes.values():
                box.configure(values=choices)

        def scan_json_sample() -> None:
            nonlocal sample_data
            try:
                path = Path(source_json_var.get()).expanduser()
                detected_fields[:] = scan_json_file(path)
                sample_data = json.loads(path.read_text(encoding="utf-8-sig"))
                if isinstance(sample_data, list):
                    sample_data = next((item for item in sample_data if isinstance(item, dict)), {})
                for item in fields_tree.get_children():
                    fields_tree.delete(item)
                for item in detected_fields:
                    rendered = json.dumps(item["sample"], ensure_ascii=False, default=str)
                    if len(rendered) > 110:
                        rendered = rendered[:107] + "..."
                    fields_tree.insert(
                        "", "end", text=item["path"], values=(item["type"], rendered)
                    )
                refresh_field_choices()
                scan_status.set(
                    f"{len(detected_fields)} field terdeteksi. Pilih field untuk mapping di bawah."
                )
                update_preview()
            except Exception as exc:
                sample_data = None
                messagebox.showerror("JSON Variable Scanner", str(exc), parent=self.root)
                scan_status.set("Scan gagal. Periksa file JSON.")

        self._button(source_row, "Scan Variables", scan_json_sample, primary=True).pack(
            side="right"
        )
        if source_json_var.get() and Path(source_json_var.get()).is_file():
            try:
                detected_fields[:] = scan_json_file(source_json_var.get())
                sample_data = json.loads(
                    Path(source_json_var.get()).read_text(encoding="utf-8-sig")
                )
                if isinstance(sample_data, list):
                    sample_data = next((item for item in sample_data if isinstance(item, dict)), {})
                for item in detected_fields:
                    rendered = json.dumps(item["sample"], ensure_ascii=False, default=str)
                    fields_tree.insert(
                        "",
                        "end",
                        text=item["path"],
                        values=(
                            item["type"],
                            rendered[:107] + "..." if len(rendered) > 110 else rendered,
                        ),
                    )
                refresh_field_choices()
                scan_status.set(f"{len(detected_fields)} field tersimpan dari scan sebelumnya.")
            except Exception:
                sample_data = None

        template_row = tk.Frame(naming_panel, bg=SURFACE)
        template_row.pack(fill="x", pady=(14, 5))
        tk.Label(
            naming_panel, text="FOLDER NAME TEMPLATE", bg=SURFACE, fg=GREEN, font=(FONT, 9, "bold")
        ).pack(anchor="w")
        template_var = tk.StringVar(value=str(naming.get("template") or DEFAULT_TEMPLATE))
        tk.Entry(
            template_row,
            textvariable=template_var,
            bg="#0A100D",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=(MONO, 9),
        ).pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 8))
        token_var = tk.StringVar(value="DATE")
        ttk.Combobox(
            template_row, textvariable=token_var, values=list(TOKENS), state="readonly", width=18
        ).pack(side="left", padx=(0, 6))

        def add_token() -> None:
            current = template_var.get().strip()
            template_var.set((current + "_" if current else "") + "{" + token_var.get() + "}")

        self._button(template_row, "Add token", add_token).pack(side="right")
        no_shift_var = tk.BooleanVar(value=bool(naming.get("no_shift", False)))
        tk.Checkbutton(
            naming_panel,
            text="No Shift — hilangkan token SESSION sepenuhnya, jangan tulis S0",
            variable=no_shift_var,
            bg=SURFACE,
            fg=TEXT,
            activebackground=SURFACE,
            activeforeground=TEXT,
            selectcolor="#0A100D",
            font=(FONT, 9),
        ).pack(anchor="w", pady=(8, 4))
        preview_var = tk.StringVar(value="Preview akan muncul setelah file JSON dipindai.")
        tk.Label(
            naming_panel,
            textvariable=preview_var,
            bg="#0A100D",
            fg=GREEN,
            font=(MONO, 9),
            anchor="w",
            justify="left",
            wraplength=900,
            padx=12,
            pady=10,
        ).pack(fill="x", pady=(8, 0))

        def current_naming_config() -> dict[str, Any]:
            field_map = {}
            for token, variable in map_vars.items():
                selected = variable.get()
                field_map[token] = DEFAULT_FIELD_MAP[token] if selected == auto_label else selected
            return {
                "source_json": source_json_var.get().strip(),
                "template": template_var.get().strip(),
                "field_map": field_map,
                "no_shift": no_shift_var.get(),
            }

        def update_preview(*_args: Any) -> None:
            if sample_data is None:
                preview_var.set("Preview akan muncul setelah file JSON dipindai.")
                return
            try:
                preview_var.set(
                    "PREVIEW  " + preview_folder_name(sample_data, current_naming_config())
                )
            except Exception as exc:
                preview_var.set("Preview belum lengkap: " + str(exc))
        template_var.trace_add("write", update_preview)
        no_shift_var.trace_add("write", update_preview)
        for variable in map_vars.values():
            variable.trace_add("write", update_preview)
        if sample_data is not None:
            update_preview()

        self._button(panel, "Save Preferences", self._save_preferences, primary=True).pack(
            anchor="w", pady=(18, 0)
        )
        self._naming_config_reader = current_naming_config
        self._set_status("Preferences siap diatur. JSON scanner hanya berjalan saat diminta.")

    def _browse_preference(self, variable: tk.StringVar, title: str) -> None:
        selected = filedialog.askdirectory(parent=self.root, title=title)
        if selected:
            variable.set(selected)

    def _save_preferences(self) -> None:
        values: dict[str, Any] = {
            key: variable.get().strip() for key, variable in self.preference_vars.items()
        }
        try:
            values["naming"] = self._naming_config_reader()
            values["naming"]["template"] = validate_template(values["naming"]["template"])
        except Exception as exc:
            messagebox.showerror("Naming Convention tidak valid", str(exc), parent=self.root)
            return
        for _key in ("source_root", "report_root", "excel_root", "organized_root"):
            value = values[_key]
            if (
                value
                and Path(value).expanduser().exists()
                and not Path(value).expanduser().is_dir()
            ):
                messagebox.showerror(
                    "Preferences tidak valid",
                    f"Path harus berupa folder:\n{value}",
                    parent=self.root,
                )
                return
        source = (
            Path(values["source_root"]).expanduser().resolve() if values["source_root"] else None
        )
        for key in ("report_root", "excel_root", "organized_root"):
            if values[key]:
                target = Path(values[key]).expanduser().resolve()
                if source and (
                    target == source or source in target.parents or target in source.parents
                ):
                    messagebox.showerror(
                        "Folder tidak aman",
                        f"{key} harus terpisah dari folder sumber:\n{target}",
                        parent=self.root,
                    )
                    return
                values[key] = str(target)
        try:
            save_preferences(values)
        except Exception as exc:
            messagebox.showerror("Gagal menyimpan Preferences", str(exc), parent=self.root)
            return
        self.preferences = values
        self.naming_preferences = dict(values["naming"])
        self.source_path.set(values["source_root"])
        self.report_path.set(values["report_root"])
        self.excel_path.set(values["excel_root"])
        self.output_path.set(values["organized_root"])
        self._set_status("Preferences berhasil disimpan.")
        messagebox.showinfo(
            "Preferences",
            "Lokasi folder dan Naming Convention berhasil disimpan.",
            parent=self.root,
        )

    def _page_activity(self) -> None:
        self._header(
            "Activity Log", "Riwayat proses lokal. Secret dan private key tidak pernah dicatat."
        )
        panel = self._panel(
            "Recent activity",
            f"{len(self.activity_entries)} event tersimpan pada profil Windows ini.",
        )
        panel.pack(fill="both", expand=True, padx=34, pady=(0, 24))
        tree = self._tree(panel, ("time", "severity", "message"), ("TIME", "LEVEL", "EVENT"))
        for item in reversed(self.activity_entries[-300:]):
            tree.insert(
                "",
                "end",
                values=(
                    item.get("time", ""),
                    item.get("severity", "INFO"),
                    item.get("message", ""),
                ),
            )
        if not self.activity_entries:
            tk.Label(
                panel, text="Belum ada aktivitas.", bg=SURFACE, fg=SECONDARY, font=(FONT, 10)
            ).pack(anchor="w", pady=(14, 0))
