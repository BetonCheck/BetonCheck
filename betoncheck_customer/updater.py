from __future__ import annotations

import requests
from .settings import APP_VERSION, UPDATES_URL


def check_for_update() -> tuple[bool, str]:
    try:
        data = requests.get(UPDATES_URL, timeout=10).json()
        latest = data.get("latest_version", APP_VERSION)
        if latest != APP_VERSION:
            return True, data.get("message", "Na voljo je nova verzija.")
        return False, "Program je posodobljen."
    except Exception as exc:
        return False, f"Preverjanje posodobitev ni uspelo: {exc}"
