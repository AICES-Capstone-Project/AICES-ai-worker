"""Shared Gemini client utilities."""

from __future__ import annotations

import os
from typing import Optional

import google.generativeai as genai

try:  # pragma: no cover - optional during tests
    from config import settings as app_settings  # type: ignore
except Exception:  # pragma: no cover
    app_settings = None

_CONFIGURED_KEY: Optional[str] = None
DEFAULT_MODEL = "gemini-2.5-flash-lite"


def resolve_api_key(explicit_key: Optional[str] = None) -> str:
    if explicit_key:
        return explicit_key
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        return env_key
    if app_settings and app_settings.gemini_api_key:
        return app_settings.gemini_api_key
    raise ValueError("GEMINI_API_KEY is required for Gemini operations")


def ensure_configured(api_key: Optional[str] = None) -> str:
    global _CONFIGURED_KEY
    resolved = resolve_api_key(api_key)
    if _CONFIGURED_KEY == resolved:
        return resolved
    genai.configure(api_key=resolved)
    _CONFIGURED_KEY = resolved
    return resolved


def get_model(model_name: str = DEFAULT_MODEL, *, api_key: Optional[str] = None) -> genai.GenerativeModel:
    ensure_configured(api_key)
    return genai.GenerativeModel(model_name)
