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
            items.append(ModuleItem(
                module_id=module_id,
                module_title=module.get("title", module_id),
                item_id=item["id"],
                title=item.get("title", item["id"]),
                file=item["file"],
                download_url=item.get("download_url", ""),
            ))
    return items


def ensure_downloaded(item: ModuleItem) -> Path:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    target = VAULT_DIR / item.file
    if target.exists():
        return target
    if not item.download_url:
        raise RuntimeError(f"Download URL is missing for {item.title}")
    response = requests.get(item.download_url, timeout=60)
    response.raise_for_status()
    target.write_bytes(response.content)
    return target
