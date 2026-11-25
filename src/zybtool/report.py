"""Deterministic JSON, HTML and CSV reporting for operators and supervisors."""

from __future__ import annotations

import csv
import html
import io
from dataclasses import asdict
from enum import Enum
from typing import Any

from zybtool.models import ResultStatus, VerificationReport
from zybtool.util import canonical_json_bytes


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: _plain(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def report_dict(report: VerificationReport) -> dict[str, Any]:
    return _plain(report)


def report_json(report: VerificationReport) -> bytes:
    return canonical_json_bytes(report_dict(report)) + b"\n"


def report_csv(report: VerificationReport) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "recording_id",
            "status",
            "trust_level",
            "device_id",
            "segment_count",
            "actual_duration_s",
            "qr_status",
            "qr_sender_authentication",
            "qr_token_id",
            "qr_time_s",
            "reasons",
        ]
    )
    for item in report.recordings:
        qr = item.qr
        writer.writerow(
            [
                item.recording_id,
                item.status.value,
                item.trust_level,
                item.device_id or "",
                len(item.segments),
                "" if item.actual_duration_s is None else f"{item.actual_duration_s:.3f}",
                qr.status.value if qr else "",
                "Tidak diautentikasi (MQ1)"
                if qr and qr.status is ResultStatus.QR_DECRYPTED
                else "",
                (qr.token_id or "") if qr else "",
                "" if not qr or qr.time_s is None else f"{qr.time_s:.3f}",
                " | ".join(item.reasons),
            ]
        )
    return output.getvalue().encode("utf-8-sig")


def report_html(report: VerificationReport) -> bytes:
    rows: list[str] = []
    for item in report.recordings:
        reasons = "<br>".join(html.escape(reason) for reason in item.reasons) or "Tidak ada"
        duration = (
            "Belum tersedia"
            if item.actual_duration_s is None
            else f"{item.actual_duration_s:.3f} s"
        )
        qr = item.qr
        qr_status = html.escape(qr.status.value if qr else "BELUM_DIPINDAI")
        signer = (
            "Tidak diautentikasi (MQ1)" if qr and qr.status is ResultStatus.QR_DECRYPTED else "-"
        )
        qr_time = f"{qr.time_s:.3f} s" if qr and qr.time_s is not None else "—"
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(item.status.value)}</strong></td>"
            f"<td><code>{html.escape(item.recording_id)}</code></td>"
            f"<td>{html.escape(item.device_id or '—')}</td>"
            f"<td>{len(item.segments)}</td>"
            f"<td>{html.escape(duration)}</td>"
            f'<td>{qr_status}<br><span class="muted">{signer} · {qr_time}</span></td>'
            f"<td>{reasons}</td>"
            "</tr>"
        )
    body = "".join(rows) or '<tr><td colspan="7">Tidak ada recording ditemukan.</td></tr>'
    source = html.escape(report.source_root)
    page = f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>ZYB Tool — Laporan Verifikasi</title>
<style>
:root{{color-scheme:dark;--bg:#080d0b;--panel:#0e1511;--line:#26372c;--text:#e8f0e9;--muted:#a0b0a4;--green:#a3f36b;}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.55 Segoe UI,Arial,sans-serif;padding:32px}}
main{{max-width:1500px;margin:auto}}h1{{font-size:26px;margin:0 0 6px}}.muted{{color:var(--muted)}}.panel{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px;margin-top:22px}}
table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:12px;border-bottom:1px solid var(--line);vertical-align:top}}th{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}}code{{font-family:Consolas,monospace;overflow-wrap:anywhere}}.notice{{color:var(--green)}}
</style></head><body><main>
<h1>ZYB Tool — Laporan Verifikasi</h1>
<div class="muted">Run {html.escape(report.run_id)} · Dibuat {html.escape(report.generated_at)}</div>
<div class="panel"><div class="muted">Folder sumber (read-only)</div><code>{source}</code>
<p class="notice">QR MQ1 berhasil didekripsi bila status QR_DECRYPTED. Format MQ1 tidak mengautentikasi identitas pembuat QR.</p></div>
<div class="panel"><table><thead><tr><th>Status</th><th>Recording</th><th>Device</th><th>Segment</th><th>Durasi aktual</th><th>Bukti QR/MQ1</th><th>Alasan / temuan</th></tr></thead>
<tbody>{body}</tbody></table></div></main></body></html>"""
    return page.encode("utf-8")
