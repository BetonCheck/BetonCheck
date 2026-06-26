from __future__ import annotations

import json
from typing import Any

from .settings import LOCAL_LICENSE_STATE_PATH


def load_license_state() -> dict[str, Any] | None:
    if not LOCAL_LICENSE_STATE_PATH.exists():
        return None

    try:
        data = json.loads(LOCAL_LICENSE_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    return data


def save_license_state(data: dict[str, Any]) -> None:
    LOCAL_LICENSE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_LICENSE_STATE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def clear_license_state() -> None:
    try:
        LOCAL_LICENSE_STATE_PATH.unlink(missing_ok=True)
    except OSError:
        pass
