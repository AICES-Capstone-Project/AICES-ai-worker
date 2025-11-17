"""Gemini-powered resume parser."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

import google.generativeai as genai

from worker.services.gemini_client import get_model

logger = logging.getLogger(__name__)


class ResumeParsingError(RuntimeError):
    """Raised when Gemini fails to parse a resume."""


def _extract_text(response: genai.types.GenerateContentResponse) -> str:
    if hasattr(response, "parts") and response.parts:
        return "".join(part.text for part in response.parts if getattr(part, "text", "")).strip()
    candidates = getattr(response, "candidates", None)
    if candidates:
        candidate = candidates[0]
        if candidate.content and candidate.content.parts:
            return "".join(part.text for part in candidate.content.parts if getattr(part, "text", "")).strip()
    raise ResumeParsingError("Gemini returned an empty response")


def _normalize_json(raw_text: str) -> Dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.debug("Gemini response was not valid JSON: %s", cleaned)
        logger.error("RAW Gemini output (first 1000 chars): %s", raw_text[:1000])
        raise ResumeParsingError("Gemini returned invalid JSON") from exc


PROMPT = """
You are an AI bot specialized in parsing resumes for software recruitment purposes.
Receive the plain text of a resume and output ONLY a valid JSON object that captures the key data.

The JSON must follow this structure:
{
    "info": "string/JSON or null",
    "education": "string/JSON or null",
    "work_experience": "string/JSON or null",
    "technical_skills": "string/JSON or null",
    "certifications": "string/JSON or null",
    "projects": "string/JSON or null",
    "languages_and_skills": "string/JSON or null"
}

Rules:
1. Return ONLY JSON (no markdown, no explanations).
2. Use null for missing data.
3. Normalize bullet points into readable sentences.
4. Prefer structured arrays when possible.
""".strip()


def ats_extractor(resume_text: str, *, api_key: str | None = None) -> Dict[str, Any]:
    """Parse a resume using Gemini and return structured JSON data."""

    model = get_model(api_key=api_key)
    prompt = f"{PROMPT}\n\nResume content:\n{resume_text}"

    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,
                max_output_tokens=8192,
            ),
        )
        raw_text = _extract_text(response)
        parsed = _normalize_json(raw_text)
        logger.debug("Parsed resume keys: %s", list(parsed.keys()))
        return parsed
    except Exception as exc:
        raise ResumeParsingError("Failed to parse resume with Gemini") from exc
