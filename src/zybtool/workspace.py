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
from zybtool.output import create_output_plan, execute_output_plan
from zybtool.pipeline import run_verification, write_report
from zybtool.settings import data_dir

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
        self.source_path = tk.StringVar(value="")
        self.report_path = tk.StringVar(value=str(Path.home() / "ZYB_Reports"))
        self.output_path = tk.StringVar(value=str(Path.home() / "ZYB_Output"))
        self.output_queue: queue.Queue[Any] = queue.Queue()
        self.output_running = False
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
            "Output & Reports": self._page_reports,
            "Activity Log": self._page_activity,
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
            ("VERIFIED", str(counts[ResultStatus.VERIFIED]) if report else "—"),
            (
                "NEEDS ATTENTION",
                str(
                    sum(
                        counts[s]
                        for s in (
                            ResultStatus.AMBIGUOUS,
                            ResultStatus.INCOMPLETE,
                            ResultStatus.METADATA_MISMATCH,
                            ResultStatus.CORRUPTED,
                            ResultStatus.QR_MISSING,
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
                fg=GREEN if label == "VERIFIED" and report else TEXT,
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
            "Discovery · metadata · video timeline · QR/MQ2 (jika key dan allow-list tersedia) · grouping · reports",
        )
        run.pack(fill="x", padx=34, pady=(0, 24))
        self.verify_status = tk.StringVar(
            value="Siap. Trusted-device allow-list bersifat opsional."
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
        self.job_running = True
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
            "Ambiguous, incomplete, mismatch, QR missing, invalid signature, replay dan corruption.",
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
            ResultStatus.INVALID_SIGNATURE,
            ResultStatus.UNKNOWN_DEVICE,
            ResultStatus.REPLAY_DETECTED,
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
        self._button(actions, "Copy report path", self._copy_report_path).pack(
            side="left", padx=(8, 0)
        )
        output_panel = self._panel(
            "Local output preparation",
            "Salin ke folder lokal baru, pertahankan nama dan isi folder sumber, lalu verifikasi SHA-256.",
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
            text="METADATA_ONLY disalin ke _UNNAMED untuk keputusan operator. Nama operasional hanya dibuat dari QR tepercaya dengan trust level 3+ dan field AITQR yang lengkap. Recording ambigu/tidak lengkap/bermasalah diblokir. Manifest hash lokal belum ditandatangani.",
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
            output_panel, "Preview & prepare local output", self._prepare_local_output, primary=True
        )
        self.output_button.pack(anchor="w", pady=(14, 0))
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
            plan = create_output_plan(self.current_report, Path(destination))
        except Exception as exc:
            messagebox.showerror("Output plan gagal", str(exc), parent=self.root)
            return
        if not plan.items:
            details = "\n".join(plan.blocked[:12]) or "Tidak ada recording yang memenuhi syarat."
            messagebox.showwarning("Tidak ada output yang aman", details, parent=self.root)
            return
        unnamed = sum(not item.named for item in plan.items)
        folder_preview = "\n".join(f"  • {item.folder_name}" for item in plan.items[:10])
        if len(plan.items) > 10:
            folder_preview += f"\n  … dan {len(plan.items) - 10} folder lainnya"
        preview = (
            f"Siap disalin: {len(plan.items)} recording\n"
            f"Dengan nama operasional dari QR: {len(plan.items) - unnamed}\n"
            f"Masuk _UNNAMED: {unnamed}\n"
            f"Diblokir: {len(plan.blocked)}\n\n"
            f"Preview folder:\n{folder_preview}\n\n"
            f"Tujuan: {plan.destination}\n\n"
            "Sumber tidak akan diubah. Folder tujuan harus baru/kosong. "
            "Tidak ada overwrite. Lanjutkan penyalinan lokal?"
        )
        if plan.blocked:
            preview += "\n\nSebagian recording diblokir karena bukti belum cukup; lihat detail pada Review Queue."
        if not messagebox.askyesno(
            "Konfirmasi penyalinan lokal", preview, icon="warning", parent=self.root
        ):
            return
        self.output_running = True
        self.output_button.configure(state="disabled")
        self.output_progress.start(12)
        self.output_status.set("Menyalin file dan memeriksa SHA-256. Jangan lepaskan media sumber.")
        self._log_activity(f"Local output copy started: {plan.destination}")

        def worker() -> None:
            try:
                result = execute_output_plan(plan, confirmed=True)
                self.output_queue.put(("success", result))
            except Exception as exc:
                self.output_queue.put(("error", str(exc)))

        threading.Thread(target=worker, name="zyb-output-copy", daemon=True).start()
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
            self._log_activity(f"Local output copy completed: {value}")
            self._set_status("Output lokal selesai dan SHA-256 cocok.")
            if hasattr(self, "output_status"):
                self.output_status.set(f"Selesai. Output: {value}")
                self.output_button.configure(state="normal")
            messagebox.showinfo(
                "Output lokal selesai",
                f"Penyalinan dan pemeriksaan SHA-256 selesai.\n\n{value}\n\nManifest berisi hash file dan belum ditandatangani.",
                parent=self.root,
            )
        else:
            self._log_activity(f"Local output copy failed: {value}", "ERROR")
            self._set_status(f"Output lokal gagal: {value}", error=True)
            if hasattr(self, "output_status"):
                self.output_status.set(f"Gagal: {value}")
                self.output_button.configure(state="normal")
            messagebox.showerror("Output lokal gagal", str(value), parent=self.root)

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
