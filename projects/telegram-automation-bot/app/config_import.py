from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover - dependency is installed in runtime env
    dotenv_values = None

from app.secure_setup import DEFAULTS
from services.secure_config import SENSITIVE_KEYS, mask_value


IMPORT_VERSION = 1
REQUIRED_IMPORT_KEYS = ("BOT_TOKEN", "OWNER_IDS")
IMPORT_KEYS = set(DEFAULTS) | set(REQUIRED_IMPORT_KEYS)


class ConfigImportError(ValueError):
    pass


def load_import_config(path: Path) -> dict[str, str]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        values = _load_json(path)
    elif suffix in {".env", ".txt"}:
        values = _load_env(path)
    else:
        raise ConfigImportError("Supported config import files: .json, .env, .txt")

    cleaned = normalize_import_values(values)
    validate_import_config(cleaned)
    return cleaned


def normalize_import_values(values: Mapping[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in values.items():
        normalized_key = str(key).strip()
        if normalized_key not in IMPORT_KEYS:
            continue
        if value is None:
            continue
        normalized_value = str(value).strip()
        if normalized_value:
            result[normalized_key] = normalized_value
    return result


def merge_import_config(existing: Mapping[str, str], imported: Mapping[str, str]) -> dict[str, str]:
    values = dict(DEFAULTS)
    values.update({key: str(value) for key, value in existing.items() if str(value).strip()})
    values.update({key: str(value) for key, value in imported.items() if str(value).strip()})
    return values


def validate_import_config(values: Mapping[str, str]) -> None:
    missing = [key for key in REQUIRED_IMPORT_KEYS if not str(values.get(key, "")).strip()]
    if missing:
        raise ConfigImportError("Missing required keys: " + ", ".join(missing))


def masked_import_config(values: Mapping[str, str]) -> dict[str, str]:
    return {
        key: mask_value(key, str(value))
        for key, value in values.items()
        if key in SENSITIVE_KEYS and str(value).strip()
    }


def _load_json(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigImportError(f"Invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigImportError("JSON config must be an object.")
    return raw


def _load_env(path: Path) -> dict[str, object]:
    if dotenv_values is not None:
        return dict(dotenv_values(path))

    result: dict[str, object] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result
