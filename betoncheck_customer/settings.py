from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "BetonCheck"
APP_VERSION = "1.0.0"

ROOT = Path(__file__).resolve().parents[1]

CONFIG_DIR = ROOT / "config"
VAULT_DIR = ROOT / "vault"
CACHE_DIR = ROOT / "cache"
TEMP_DIR = ROOT / "temp"
LOGS_DIR = ROOT / "logs"

PROJECTS_DIR = ROOT / "Projects"

LICENSE_URL = (
    "https://raw.githubusercontent.com/"
    "BetonCheck/BetonCheckLicense/refs/heads/master/licenses_signed.json"
)

LICENSE_SERVER_URL = os.environ.get(
    "BETONCHECK_LICENSE_SERVER_URL",
    "https://betoncheck.bolt.host",
).rstrip("/")
LICENSE_HEARTBEAT_INTERVAL_SECONDS = 300
LICENSE_OFFLINE_GRACE_DAYS = 7

MODULES_URL = (
    "https://raw.githubusercontent.com/"
    "BetonCheck/BetonCheckLicense/refs/heads/master/modules.json"
)

UPDATES_URL = (
    "https://raw.githubusercontent.com/"
    "BetonCheck/BetonCheckLicense/refs/heads/master/updates.json"
)

PUBLIC_KEY_PATH = CONFIG_DIR / "public_key.pem"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
LOCAL_LICENSE_KEY_PATH = CONFIG_DIR / "license_key.txt"
LOCAL_LICENSE_STATE_PATH = CONFIG_DIR / "license_state.json"
LAUNCHER_PRIVATE_KEY_PATH = CONFIG_DIR / "launcher_private_key.pem"
