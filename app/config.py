"""Chemins et configuration partagés ; aucun accès MySQL à l'import."""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
STATE_DIR = ROOT_DIR / "var"
SESSION_FILE = STATE_DIR / "session.json"


def setting(name, default=""):
    if name in os.environ:
        return os.environ[name]
    path = ROOT_DIR / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.strip() == name:
                    return value.strip().strip("\"'")
    return default


def database_settings():
    if not setting('DB_USER') or not setting('DB_NAME'):
        raise ValueError('Renseignez DB_USER et DB_NAME dans .env avant de vous connecter à MySQL.')
    return {"host": setting("DB_HOST", "localhost"),
            "port": int(setting("DB_PORT", "3306")),
            "user": setting("DB_USER"),
            "password": setting("DB_PASSWORD"),
            "database": setting("DB_NAME", "e_commerce")}


def admin_credentials():
    username, password = setting('GROUP9_ADMIN_USER'), setting('GROUP9_ADMIN_PASSWORD')
    if not username or len(password) < 12:
        raise ValueError('Configurez GROUP9_ADMIN_USER et un GROUP9_ADMIN_PASSWORD d’au moins 12 caractères dans .env.')
    return username, password
