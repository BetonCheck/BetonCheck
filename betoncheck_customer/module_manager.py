from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import requests

from .settings import MODULES_URL, VAULT_DIR, CACHE_DIR


@dataclass
class ModuleItem:
    module_id: str
    module_title: str
    item_id: str
    title: str
    file: str
    download_url: str


def fetch_modules() -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / "modules.json"

    try:
        response = requests.get(MODULES_URL, timeout=15)
        response.raise_for_status()

        cache_file.write_text(response.text, encoding="utf-8")
        return response.json()

    except Exception:
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))
        raise


def available_items(licensed_modules: list[str]) -> list[ModuleItem]:
    data = fetch_modules().get("modules", {})
    items: list[ModuleItem] = []

    for module_id in licensed_modules:
        module = data.get(module_id)

        if not module:
            continue

        for item in module.get("items", []):
            items.append(
                ModuleItem(
                    module_id=module_id,
                    module_title=module.get("title", module_id),
                    item_id=item["id"],
                    title=item.get("title", item["id"]),
                    file=item["file"],
                    download_url=item.get("download_url", ""),
                )
            )

    return items


def ensure_downloaded(item: ModuleItem) -> Path:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)

    target = VAULT_DIR / item.file

    print("=== BetonCheck download debug ===")
    print("Item title:", item.title)
    print("Item file:", item.file)
    print("Local target:", target)
    print("Download URL:", item.download_url)

    if target.exists():
        print("Status: local file already exists")
        return target

    if not item.download_url:
        raise RuntimeError(
            f"Download URL manjka za modul '{item.title}'. "
            f"Preveri modules.json."
        )

    # Pomembno: ustvari tudi podmape, npr. vault/beam_design/
    target.parent.mkdir(parents=True, exist_ok=True)

    response = requests.get(item.download_url, timeout=60)

    print("HTTP status:", response.status_code)
    print("Content-Type:", response.headers.get("content-type", ""))
    print("First bytes:", response.content[:40])

    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    text_start = response.content[:100].decode("utf-8", errors="ignore").lower()

    if "text/html" in content_type or "<!doctype html" in text_start or "<html" in text_start:
        raise RuntimeError(
            "GitHub ni vrnil .bckx datoteke, ampak HTML stran. "
            "Najverjetneje je download_url napačen ali datoteka ni na tej poti."
        )

    if len(response.content) < 100:
        raise RuntimeError(
            f"Prenesena datoteka je sumljivo majhna ({len(response.content)} bytes). "
            "Preveri, ali URL kaže na pravo .bckx datoteko."
        )

    target.write_bytes(response.content)

    return target