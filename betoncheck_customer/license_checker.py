from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import date
from typing import Any

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .settings import LICENSE_URL, PUBLIC_KEY_PATH, LOCAL_LICENSE_KEY_PATH


@dataclass
class LicenseResult:
    valid: bool
    message: str
    key: str | None = None
    customer: str | None = None
    valid_until: str | None = None
    modules: dict[str, dict[str, Any]] | None = None


def save_license_key(key: str) -> None:
    LOCAL_LICENSE_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_LICENSE_KEY_PATH.write_text(key.strip(), encoding="utf-8")


def load_license_key() -> str | None:
    if LOCAL_LICENSE_KEY_PATH.exists():
        return LOCAL_LICENSE_KEY_PATH.read_text(encoding="utf-8").strip()

    return None


def fetch_signed_licenses() -> dict:
    response = requests.get(LICENSE_URL, timeout=15)
    response.raise_for_status()
    return response.json()


def verify_and_decode(signed: dict) -> dict:
    payload_b64 = signed["payload_b64"]
    signature_b64 = signed["signature_b64"]

    payload = base64.b64decode(payload_b64)
    signature = base64.b64decode(signature_b64)

    public_key = serialization.load_pem_public_key(
        PUBLIC_KEY_PATH.read_bytes()
    )

    public_key.verify(
        signature,
        payload,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )

    return json.loads(payload.decode("utf-8"))


def normalize_modules(raw_modules: Any) -> dict[str, dict[str, Any]]:
    """
    Nova oblika:
        "modules": {
            "beam_design": {"key": "..."}
        }

    Stara oblika:
        "modules": ["beam_design"]

    Staro obliko še sprejmemo, ampak brez ključev ne bo mogoče
    dešifrirati modulov. To je samo za bolj jasno napako.
    """

    if raw_modules is None:
        return {}

    if isinstance(raw_modules, dict):
        return raw_modules

    if isinstance(raw_modules, list):
        return {
            str(module_id): {}
            for module_id in raw_modules
        }

    return {}


def check_license(key: str | None = None) -> LicenseResult:
    key = key or load_license_key()

    if not key:
        return LicenseResult(False, "Licenčni ključ ni vpisan.")

    try:
        signed = fetch_signed_licenses()
        payload = verify_and_decode(signed)

    except Exception as exc:
        return LicenseResult(
            False,
            f"Licence ni bilo mogoče preveriti: {exc}",
        )

    for lic in payload.get("licenses", []):
        if lic.get("key") != key:
            continue

        if lic.get("status") != "active":
            return LicenseResult(False, "Licenca ni aktivna.")

        valid_until = lic.get("valid_until")

        try:
            until = date.fromisoformat(valid_until)
        except Exception:
            return LicenseResult(
                False,
                "Datum veljavnosti licence ni pravilen.",
            )

        if date.today() > until:
            return LicenseResult(
                False,
                f"Licenca je potekla dne {valid_until}.",
            )

        modules = normalize_modules(lic.get("modules"))

        save_license_key(key)

        return LicenseResult(
            valid=True,
            message="Licenca je veljavna.",
            key=key,
            customer=lic.get("customer"),
            valid_until=valid_until,
            modules=modules,
        )

    return LicenseResult(False, "Licenčni ključ ne obstaja.")