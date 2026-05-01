from __future__ import annotations

import base64
import json
import os
from pathlib import Path


APP_DIR = Path(os.getenv("APPDATA", Path.home())) / "ClientSGI"
STATE_FILE = APP_DIR / "state.json"


def _ensure_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def _protect_windows(value: str) -> str:
    if os.name != "nt":
        return value
    try:
        import win32crypt  # type: ignore
    except Exception:
        return value
    encrypted = win32crypt.CryptProtectData(value.encode("utf-8"), "clientsgi", None, None, None, 0)
    return base64.b64encode(encrypted).decode("ascii")


def _unprotect_windows(value: str) -> str:
    if os.name != "nt":
        return value
    try:
        import win32crypt  # type: ignore
    except Exception:
        return value
    try:
        decrypted = win32crypt.CryptUnprotectData(base64.b64decode(value), None, None, None, 0)[1]
        return decrypted.decode("utf-8")
    except Exception:
        return value


def load_state() -> dict:
    _ensure_dir()
    if not STATE_FILE.exists():
        return {
            "base_url": "https://sgi.seds.sp.gov.br",
            "token": "",
            "since_id": 0,
            "username": "",
        }
    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    token = data.get("token", "")
    if token:
        data["token"] = _unprotect_windows(token)
    return data


def save_state(state: dict) -> None:
    _ensure_dir()
    payload = dict(state)
    token = payload.get("token", "")
    if token:
        payload["token"] = _protect_windows(token)
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

