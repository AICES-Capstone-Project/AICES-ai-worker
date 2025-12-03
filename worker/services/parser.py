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


# ============================================================================
# FIX #5: Improved parser with standardized field structure
# ============================================================================

PROMPT = """
You are an AI bot specialized in parsing resumes for software recruitment purposes.
Receive the plain text of a resume and output ONLY a valid JSON object that captures the key data.

════════════════════════════════════════════════════════════════════════════════
IMPORTANT: Use these EXACT field names (in English) for the JSON output.
These field names are standardized for scoring criteria matching.
════════════════════════════════════════════════════════════════════════════════

The JSON must follow this EXACT structure:
{
    "info": {
        "fullName": "<candidate's full name>",
        "email": "<email address>",
        "phone": "<phone number>",
        "location": "<city, country>",
        "linkedin": "<LinkedIn URL or null>",
        "portfolio": "<portfolio/website URL or null>"
    },
    "education": [
        {
            "degree": "<degree name, e.g., Bachelor of Science>",
            "field": "<field of study, e.g., Computer Science>",
            "institution": "<university/college name>",
            "graduationYear": "<year or 'Present'>",
            "gpa": "<GPA if mentioned, else null>"
        }
    ],
    "work_experience": [
        {
            "title": "<job title>",
            "company": "<company name>",
            "location": "<city, country or 'Remote'>",
            "startDate": "<YYYY-MM or YYYY>",
            "endDate": "<YYYY-MM or 'Present'>",
            "duration": "<calculated duration, e.g., '2 years 3 months'>",
            "responsibilities": ["<responsibility 1>", "<responsibility 2>"],
            "achievements": ["<achievement 1>", "<achievement 2>"]
        }
    ],
    "technical_skills": {
        "programming_languages": ["<language 1>", "<language 2>"],
        "frameworks": ["<framework 1>", "<framework 2>"],
        "databases": ["<database 1>", "<database 2>"],
        "tools": ["<tool 1>", "<tool 2>"],
        "cloud": ["<AWS>", "<Azure>", "<GCP>"],
        "other": ["<other skills>"]
    },
    "certifications": [
        {
            "name": "<certification name>",
            "issuer": "<issuing organization>",
            "date": "<date obtained or null>",
            "expiryDate": "<expiry date or null>"
        }
    ],
    "projects": [
        {
            "name": "<project name>",
            "description": "<brief description>",
            "technologies": ["<tech 1>", "<tech 2>"],
            "url": "<GitHub/demo URL or null>"
        }
    ],
    "languages_and_skills": [
        {
            "language": "<language name>",
            "proficiency": "<Native/Fluent/Intermediate/Basic>"
        }
    ],
    "summary": "<professional summary if present, else null>",
    "total_experience_years": <number - calculate total years of work experience>
}

════════════════════════════════════════════════════════════════════════════════
PARSING RULES
════════════════════════════════════════════════════════════════════════════════

1. Return ONLY valid JSON (no markdown, no explanations, no comments).
2. Use null for missing data (not empty strings).
3. Use empty arrays [] for missing lists.
4. Normalize bullet points into readable sentences.
5. Calculate total_experience_years by summing all work experience durations.
6. Parse dates consistently: prefer YYYY-MM format, use "Present" for current positions.
7. Separate responsibilities from achievements (achievements have metrics/impact).
8. Categorize technical skills properly (languages vs frameworks vs tools).
9. Extract ALL information - do not summarize or truncate.
10. If the resume is in a non-English language, extract the content as-is but use English field names.
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
        
        # Ensure required fields exist with defaults
        parsed = _ensure_required_fields(parsed)
        
        logger.debug("Parsed resume keys: %s", list(parsed.keys()))
        return parsed
    except Exception as exc:
        raise ResumeParsingError("Failed to parse resume with Gemini") from exc


def _ensure_required_fields(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all required fields exist in the parsed resume.
    
    This helps prevent KeyError when scoring criteria try to access fields.
    """
    defaults = {
        "info": {},
        "education": [],
        "work_experience": [],
        "technical_skills": {},
        "certifications": [],
        "projects": [],
        "languages_and_skills": [],
        "summary": None,
        "total_experience_years": 0
    }
    
    for key, default_value in defaults.items():
        if key not in parsed or parsed[key] is None:
            parsed[key] = default_value
    
    # Ensure info has sub-fields
    if isinstance(parsed.get("info"), dict):
        info_defaults = {
            "fullName": None,
            "email": None,
            "phone": None,
            "location": None,
            "linkedin": None,
            "portfolio": None
        }
        for key, default_value in info_defaults.items():
            if key not in parsed["info"]:
                parsed["info"][key] = default_value
    
    # Ensure technical_skills has sub-fields
    if isinstance(parsed.get("technical_skills"), dict):
        skills_defaults = {
            "programming_languages": [],
            "frameworks": [],
            "databases": [],
            "tools": [],
            "cloud": [],
            "other": []
        }
        for key, default_value in skills_defaults.items():
            if key not in parsed["technical_skills"]:
                parsed["technical_skills"][key] = default_value
    
    return parsed
