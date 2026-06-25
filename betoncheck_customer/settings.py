from __future__ import annotations

from pathlib import Path

APP_NAME = "BetonCheck"
APP_VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
VAULT_DIR = ROOT / "vault"
CACHE_DIR = ROOT / "cache"
TEMP_DIR = ROOT / "temp"
LOGS_DIR = ROOT / "logs"

LICENSE_URL = "https://raw.githubusercontent.com/USERNAME/betoncheck-license-public/main/licenses_signed.json"
MODULES_URL = "https://raw.githubusercontent.com/USERNAME/betoncheck-license-public/main/modules.json"
UPDATES_URL = "https://raw.githubusercontent.com/USERNAME/betoncheck-license-public/main/updates.json"

PUBLIC_KEY_PATH = CONFIG_DIR / "public_key.pem"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
LOCAL_LICENSE_KEY_PATH = CONFIG_DIR / "license_key.txt"
APP_SECRET = "CHANGE_THIS_BEFORE_BUILDING_EXE"
