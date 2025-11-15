"""Application configuration loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"

load_dotenv()


@dataclass(frozen=True)
class Settings:
    redis_url: str
    backend_api_url: str
    gemini_api_key: str


def _read_yaml_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def load_settings(config_path: Path = CONFIG_PATH) -> Settings:
    yaml_config = _read_yaml_config(config_path)

    redis_url = os.getenv("REDIS_HOST") or yaml_config.get(
        "REDIS_HOST") or "redis://localhost:6379"
    backend_api_url = os.getenv("BACKEND_API_URL") or yaml_config.get(
        "BACKEND_API_URL") or "http://localhost:5000"
    gemini_api_key = os.getenv(
        "GEMINI_API_KEY") or yaml_config.get("GEMINI_API_KEY") or ""

    return Settings(
        redis_url=redis_url,
        backend_api_url=backend_api_url.rstrip("/"),
        gemini_api_key=gemini_api_key,
    )


settings = load_settings()
