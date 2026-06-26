from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

from .device_id import get_device_id_hash, get_device_name
from .license_state import load_license_state, save_license_state, clear_license_state
from .settings import (
    APP_VERSION,
    LICENSE_HEARTBEAT_INTERVAL_SECONDS,
    LICENSE_OFFLINE_GRACE_DAYS,
    LICENSE_SERVER_URL,
    LOCAL_LICENSE_KEY_PATH,
)


REQUEST_TIMEOUT_SECONDS = 15
REASON_ACTIVE_ELSEWHERE = "license_active_on_another_device"
REASON_OFFLINE_GRACE_EXPIRED = "offline_grace_expired"
REASON_MISSING_SESSION = "missing_session_token"
REASON_SERVER_UNREACHABLE = "server_unreachable"


@dataclass
class LicenseResult:
    valid: bool
    message: str
    key: str | None = None
    customer: str | None = None
    valid_until: str | None = None
    modules: dict[str, dict[str, Any]] | None = None
    session_token: str | None = None
    reason: str | None = None


def save_license_key(key: str) -> None:
    LOCAL_LICENSE_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_LICENSE_KEY_PATH.write_text(key.strip(), encoding="utf-8")


def load_license_key() -> str | None:
    state = load_license_state()
    if state is not None:
        key = state.get("license_key")
        if isinstance(key, str) and key.strip():
            return key.strip()

    if LOCAL_LICENSE_KEY_PATH.exists():
        return LOCAL_LICENSE_KEY_PATH.read_text(encoding="utf-8").strip()

    return None


def check_license(key: str | None = None) -> LicenseResult:
    return activate_license(key or load_license_key() or "")


def activate_license(license_key: str) -> LicenseResult:
    license_key = license_key.strip()
    if not license_key:
        return LicenseResult(False, "Licenčni ključ ni vpisan.")

    payload = {
        "license_key": license_key,
        "device_id_hash": get_device_id_hash(),
        "device_name": get_device_name(),
        "app_version": APP_VERSION,
    }

    try:
        data = _post_json("/api/license/activate", payload)
    except requests.RequestException as exc:
        return LicenseResult(
            False,
            f"Licence ni bilo mogoče preveriti. Preverite internetno povezavo. ({exc})",
            key=license_key,
            reason=REASON_SERVER_UNREACHABLE,
        )
    except ValueError as exc:
        return LicenseResult(
            False,
            f"Licenčni strežnik je vrnil neveljaven odgovor: {exc}",
            key=license_key,
        )

    if not _response_is_valid(data):
        return _invalid_result_from_response(data, license_key)

    session_token = _as_text(data.get("session_token") or data.get("sessionToken"))
    if not session_token:
        return LicenseResult(
            False,
            "Licenčni strežnik ni vrnil sejne oznake.",
            key=license_key,
            reason=REASON_MISSING_SESSION,
        )

    result = _valid_result_from_response(data, license_key, session_token)
    _save_successful_state(result)
    save_license_key(license_key)
    return result


def heartbeat_license() -> LicenseResult:
    state = load_license_state()
    if state is None:
        return LicenseResult(
            False,
            "Licenca ni aktivirana.",
            reason=REASON_MISSING_SESSION,
        )

    license_key = _as_text(state.get("license_key"))
    session_token = _as_text(state.get("session_token"))
    device_id_hash = _as_text(state.get("device_id_hash"))

    if not license_key or not session_token or not device_id_hash:
        clear_license_state()
        return LicenseResult(
            False,
            "Manjkajo podatki licenčne seje. Licenco aktivirajte znova.",
            key=license_key,
            reason=REASON_MISSING_SESSION,
        )

    payload = {
        "license_key": license_key,
        "device_id_hash": device_id_hash,
        "session_token": session_token,
        "app_version": APP_VERSION,
    }

    try:
        data = _post_json("/api/license/heartbeat", payload)
    except requests.RequestException:
        return _offline_grace_result(state)
    except ValueError as exc:
        return LicenseResult(
            False,
            f"Licenčni strežnik je vrnil neveljaven odgovor: {exc}",
            key=license_key,
        )

    if not _response_is_valid(data):
        reason = _response_reason(data)
        if reason == REASON_ACTIVE_ELSEWHERE:
            clear_license_state()
            return LicenseResult(
                False,
                "Licenca je aktivna na drugi napravi. Ta seja ni več veljavna.",
                key=license_key,
                reason=REASON_ACTIVE_ELSEWHERE,
            )

        return _invalid_result_from_response(data, license_key)

    session_token = _as_text(data.get("session_token") or data.get("sessionToken")) or session_token
    result = _valid_result_from_response(data, license_key, session_token, fallback_state=state)
    _save_successful_state(result)
    return result


def deactivate_license() -> None:
    state = load_license_state()
    if state is None:
        clear_license_state()
        _clear_legacy_license_key()
        return

    license_key = _as_text(state.get("license_key"))
    session_token = _as_text(state.get("session_token"))
    device_id_hash = _as_text(state.get("device_id_hash")) or get_device_id_hash()

    if license_key and session_token:
        try:
            _post_json(
                "/api/license/deactivate",
                {
                    "license_key": license_key,
                    "device_id_hash": device_id_hash,
                    "session_token": session_token,
                    "app_version": APP_VERSION,
                },
            )
        except (requests.RequestException, ValueError):
            pass

    clear_license_state()
    _clear_legacy_license_key()


def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if LICENSE_SERVER_URL == "https://YOUR-LICENSE-SITE.com":
        raise requests.RequestException(
            "LICENSE_SERVER_URL ni nastavljen. Nastavite BETONCHECK_LICENSE_SERVER_URL."
        )

    url = f"{LICENSE_SERVER_URL}{path}"
    response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)

    try:
        data = response.json()
    except ValueError as exc:
        response.raise_for_status()
        raise ValueError("odgovor ni JSON") from exc

    if response.status_code >= 500:
        raise requests.HTTPError(
            f"Licenčni strežnik trenutno ni dosegljiv ({response.status_code}).",
            response=response,
        )

    return data


def _response_is_valid(data: dict[str, Any]) -> bool:
    if data.get("valid") is True or data.get("success") is True:
        return True

    status = _as_text(data.get("status"))
    return status in {"active", "valid", "ok"}


def _invalid_result_from_response(data: dict[str, Any], license_key: str | None) -> LicenseResult:
    reason = _response_reason(data)
    message = _as_text(data.get("message")) or _message_for_reason(reason)

    return LicenseResult(
        False,
        message,
        key=license_key,
        reason=reason,
    )


def _valid_result_from_response(
    data: dict[str, Any],
    license_key: str,
    session_token: str,
    fallback_state: dict[str, Any] | None = None,
) -> LicenseResult:
    fallback_state = fallback_state or {}

    customer = (
        _as_text(data.get("customer_name"))
        or _as_text(data.get("customer"))
        or _as_text(fallback_state.get("customer_name"))
    )
    valid_until = _as_text(data.get("valid_until")) or _as_text(fallback_state.get("valid_until"))
    modules = normalize_modules(data.get("modules", fallback_state.get("modules")))

    return LicenseResult(
        True,
        "Licenca je veljavna.",
        key=license_key,
        customer=customer,
        valid_until=valid_until,
        modules=modules,
        session_token=session_token,
    )


def _save_successful_state(result: LicenseResult) -> None:
    save_license_state(
        {
            "license_key": result.key,
            "session_token": result.session_token,
            "customer_name": result.customer,
            "valid_until": result.valid_until,
            "modules": result.modules or {},
            "last_success_utc": _utc_now().isoformat(),
            "device_id_hash": get_device_id_hash(),
        }
    )


def normalize_modules(raw_modules: Any) -> dict[str, dict[str, Any]]:
    if raw_modules is None:
        return {}

    if isinstance(raw_modules, dict):
        result: dict[str, dict[str, Any]] = {}
        for module_id, module_data in raw_modules.items():
            if isinstance(module_data, dict):
                result[str(module_id)] = module_data
            elif isinstance(module_data, str):
                result[str(module_id)] = {"encrypted_key": module_data}
            else:
                result[str(module_id)] = {}
        return result

    if isinstance(raw_modules, list):
        result = {}
        for item in raw_modules:
            if isinstance(item, dict):
                module_id = item.get("id") or item.get("module_id") or item.get("name")
                if module_id:
                    result[str(module_id)] = item
            else:
                result[str(item)] = {}
        return result

    return {}


def _offline_grace_result(state: dict[str, Any]) -> LicenseResult:
    license_key = _as_text(state.get("license_key"))
    last_success = _parse_datetime(_as_text(state.get("last_success_utc")))

    if last_success is None:
        return LicenseResult(
            False,
            "Licence ni bilo mogoče preveriti. Povežite se z internetom.",
            key=license_key,
            reason=REASON_OFFLINE_GRACE_EXPIRED,
        )

    if _utc_now() - last_success > timedelta(days=LICENSE_OFFLINE_GRACE_DAYS):
        return LicenseResult(
            False,
            "Licence ni bilo mogoče preveriti. Povežite se z internetom.",
            key=license_key,
            reason=REASON_OFFLINE_GRACE_EXPIRED,
        )

    return LicenseResult(
        True,
        (
            "Licenčnega strežnika ni bilo mogoče doseči. "
            f"Uporabljam začasni offline dostop do {LICENSE_OFFLINE_GRACE_DAYS} dni."
        ),
        key=license_key,
        customer=_as_text(state.get("customer_name")),
        valid_until=_as_text(state.get("valid_until")),
        modules=normalize_modules(state.get("modules")),
        session_token=_as_text(state.get("session_token")),
        reason=REASON_SERVER_UNREACHABLE,
    )


def _response_reason(data: dict[str, Any]) -> str | None:
    return _as_text(data.get("reason") or data.get("code") or data.get("error"))


def _message_for_reason(reason: str | None) -> str:
    messages = {
        REASON_ACTIVE_ELSEWHERE: "Licenca je aktivna na drugi napravi. Ta seja ni več veljavna.",
        "expired": "Licenca je potekla.",
        "blocked": "Licenca je blokirana.",
        "invalid_license": "Licenčni ključ ni veljaven.",
        "invalid_session": "Licenčna seja ni več veljavna.",
        REASON_MISSING_SESSION: "Manjkajo podatki licenčne seje.",
    }

    return messages.get(reason or "", "Licenca ni aktivna.")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _clear_legacy_license_key() -> None:
    try:
        LOCAL_LICENSE_KEY_PATH.unlink(missing_ok=True)
    except OSError:
        pass
