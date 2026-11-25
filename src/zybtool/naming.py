"""Configurable, deterministic operational folder naming for Arrange Folder."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

TOKENS = ("DATE", "LOCATION_CODE", "PERSON_NAME", "DEVICE_ID", "SESSION", "ACTIVITY")
DEFAULT_TEMPLATE = "{DATE}_{LOCATION_CODE}_{PERSON_NAME}_{DEVICE_ID}_{SESSION}_{ACTIVITY}"
DEFAULT_FIELD_MAP = {
    "DATE": "",
    "LOCATION_CODE": "b",
    "PERSON_NAME": "r",
    "DEVICE_ID": "dn",
    "SESSION": "sh",
    "ACTIVITY": "a",
}
DEFAULT_CONFIG = {
    "source_json": "",
    "template": DEFAULT_TEMPLATE,
    "field_map": dict(DEFAULT_FIELD_MAP),
    "no_shift": False,
}


def _walk(value: Any, prefix: str = "", depth: int = 0):
    if depth > 12:
        return
    if isinstance(value, dict):
        for key in sorted(value, key=lambda item: str(item).casefold()):
            path = f"{prefix}.{key}" if prefix else str(key)
            child = value[key]
            yield path, child
            yield from _walk(child, path, depth + 1)
    elif isinstance(value, list):
        for index, child in enumerate(value[:50]):
            path = f"{prefix}[{index}]"
            yield path, child
            yield from _walk(child, path, depth + 1)


def scan_json_file(path: str | Path) -> list[dict[str, Any]]:
    """Read a user-selected JSON sample and return stable nested field paths."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"File JSON tidak ditemukan: {source}")
    if source.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("File JSON terlalu besar untuk scanner (maksimum 10 MB).")
    try:
        value = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON tidak dapat dibaca ({type(exc).__name__}).") from None
    if not isinstance(value, (dict, list)):
        raise ValueError("Akar JSON harus berupa object atau array.")
    fields = []
    for field_path, sample in _walk(value):
        fields.append(
            {
                "path": field_path,
                "type": _value_type(sample),
                "sample": sample if isinstance(sample, (str, int, float, bool)) or sample is None
                else ("object" if isinstance(sample, dict) else f"array[{len(sample)}]"),
            }
        )
    return fields


def _value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"


def read_json_path(value: Any, path: str) -> Any:
    if not path:
        return None
    current = value
    parts = [part for part in path.replace("[", ".").replace("]", "").split(".") if part]
    for part in parts:
        if part.isdigit():
            if not isinstance(current, list) or int(part) >= len(current):
                return None
            current = current[int(part)]
        else:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        if current is None:
            return None
    return current


def _resolve_path(path: str, session: dict[str, Any], payload: dict[str, Any]) -> Any:
    if path.startswith("session."):
        return read_json_path(session, path[8:])
    if path.startswith("qr."):
        return read_json_path(payload, path[3:])
    # Unqualified paths prefer the verified QR payload, then native camera metadata.
    value = read_json_path(payload, path)
    return value if value not in (None, "") else read_json_path(session, path)


def _safe_component(value: Any, field: str) -> str:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"Variabel {field} kosong atau tidak valid.")
    if isinstance(value, (dict, list)):
        raise ValueError(f"Variabel {field} bukan nilai sederhana.")
    result = re.sub(r"[^A-Za-z0-9]", "", str(value).strip())
    if not result:
        raise ValueError(f"Variabel {field} tidak memiliki karakter alfanumerik.")
    if result.upper() in {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        raise ValueError(f"Variabel {field} memakai nama perangkat Windows yang dilarang.")
    return result


def _date_component(value: Any) -> str:
    if value is None or isinstance(value, bool):
        raise ValueError("Tanggal capture tidak tersedia atau ambigu.")
    if isinstance(value, (int, float)):
        from datetime import UTC, datetime

        value = datetime.fromtimestamp(float(value), UTC).strftime("%Y%m%d")
    digits = re.sub(r"[^0-9]", "", str(value))
    if len(digits) >= 8:
        digits = digits[:8]
    if len(digits) != 8:
        raise ValueError("Tanggal harus dapat dibaca sebagai YYYYMMDD.")
    return digits


def validate_template(template: str) -> str:
    value = str(template or "").strip()
    if not value:
        raise ValueError("Template nama folder tidak boleh kosong.")
    found = re.findall(r"\{([A-Z_]+)\}", value)
    unknown = sorted(set(found) - set(TOKENS))
    if unknown:
        raise ValueError("Token tidak dikenal: " + ", ".join(unknown))
    residue = re.sub(r"\{[A-Z_]+\}", "", value)
    if re.search(r"[^A-Za-z0-9_. -]", residue) or "/" in residue or "\\" in residue:
        raise ValueError("Separator hanya boleh huruf, angka, spasi, titik, garis bawah, atau tanda hubung.")
    if not found:
        raise ValueError("Template harus memiliki minimal satu token.")
    return value


def build_folder_name(
    payload: dict[str, Any],
    session: dict[str, Any],
    capture_date: str | None,
    config: dict[str, Any] | None = None,
) -> str:
    """Render a safe folder name from verified QR data and native session.json."""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    field_map = {**DEFAULT_FIELD_MAP, **(cfg.get("field_map") or {})}
    template = validate_template(str(cfg.get("template") or DEFAULT_TEMPLATE))

    # Keep the existing QR contract checks even when the operator customizes the
    # display template; customization must never weaken verification requirements.
    branch = _safe_component(payload.get("b"), "b")
    recorder = _safe_component(payload.get("r"), "r")
    recorder_number = _safe_component(payload.get("dn"), "dn")
    activity = _safe_component(payload.get("a"), "a")
    shift = payload.get("sh")
    if not re.fullmatch(r"MM[0-9]{2,4}", branch):
        raise ValueError("Field AITQR 'b' harus berformat MM diikuti 2–4 digit.")
    if not re.fullmatch(r"ZY[0-9]{3,4}", recorder_number):
        raise ValueError("Field AITQR 'dn' harus berformat ZY diikuti 3–4 digit.")
    if not isinstance(shift, int) or isinstance(shift, bool) or shift not in (1, 2, 3):
        raise ValueError("Field AITQR 'sh' harus bernilai 1, 2, atau 3.")

    values: dict[str, str] = {"DATE": _date_component(capture_date)}
    defaults = {
        "LOCATION_CODE": branch,
        "PERSON_NAME": recorder,
        "DEVICE_ID": recorder_number,
        "SESSION": str(shift),
        "ACTIVITY": activity,
    }
    for token in TOKENS[1:]:
        path = str(field_map.get(token) or "").strip()
        raw = _resolve_path(path, session, payload) if path else defaults[token]
        values[token] = _safe_component(raw, token)

    if bool(cfg.get("no_shift")):
        values.pop("SESSION", None)
    else:
        values["SESSION"] = "S" + values["SESSION"]

    rendered = template
    for token in TOKENS:
        rendered = rendered.replace("{" + token + "}", values.get(token, ""))
    rendered = re.sub(r"[_ .-]{2,}", lambda match: match.group(0)[0], rendered)
    rendered = rendered.strip("_. -")
    if not rendered or rendered in {".", ".."}:
        raise ValueError("Template tidak menghasilkan nama folder yang valid.")
    if len(rendered) > 180:
        raise ValueError("Nama folder melebihi 180 karakter.")
    return rendered


def preview_folder_name(sample: Any, config: dict[str, Any] | None = None) -> str:
    """Render a Preferences preview from the selected JSON sample without moving files."""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    sample_dict = sample if isinstance(sample, dict) else {}
    payload = sample_dict.get("qr") if isinstance(sample_dict.get("qr"), dict) else sample_dict
    session = sample_dict.get("session") if isinstance(sample_dict.get("session"), dict) else sample_dict
    field_map = {**DEFAULT_FIELD_MAP, **(cfg.get("field_map") or {})}
    template = validate_template(str(cfg.get("template") or DEFAULT_TEMPLATE))
    date_value = None
    date_path = str(field_map.get("DATE") or "").strip()
    if date_path:
        date_value = _resolve_path(date_path, session, payload)
    if date_value is None:
        date_value = session.get("capture_date") or session.get("created_iso") or "20261125"
    values: dict[str, str] = {"DATE": _date_component(date_value)}
    defaults = {"LOCATION_CODE": "b", "PERSON_NAME": "r", "DEVICE_ID": "dn", "SESSION": "sh", "ACTIVITY": "a"}
    for token, key in defaults.items():
        path = str(field_map.get(token) or "").strip()
        raw = _resolve_path(path, session, payload) if path else payload.get(key)
        if raw is None:
            raw = "{" + token + "}"
        else:
            raw = _safe_component(raw, token)
            if token == "SESSION":
                raw = "S" + raw
        values[token] = str(raw)
    if bool(cfg.get("no_shift")):
        values.pop("SESSION", None)
    rendered = template
    for token in TOKENS:
        rendered = rendered.replace("{" + token + "}", values.get(token, ""))
    rendered = re.sub(r"[_ .-]{2,}", lambda match: match.group(0)[0], rendered).strip("_. -")
    return rendered or "(preview tidak tersedia)"
