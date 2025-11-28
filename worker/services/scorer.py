"""AI scoring module using Gemini."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import google.generativeai as genai

from worker.services.gemini_client import get_model

logger = logging.getLogger(__name__)

# Maximum length for requirements text to prevent token limit issues
MAX_REQUIREMENTS_LENGTH = 5000


class AIScoringError(RuntimeError):
    """Raised when the AI scoring step fails."""


def _clean_ai_response(raw_text: str) -> Dict[str, Any]:
    """Clean and parse AI response, stripping markdown fences."""
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
        # Log raw text for debugging (truncate to 5000 chars to avoid log spam)
        logger.error(
            "Invalid JSON from Gemini (first 5000 chars): %s",
            raw_text[:5000] if len(raw_text) > 5000 else raw_text
        )
        raise AIScoringError(
            "Gemini returned invalid JSON during scoring") from exc


CRITERIA_SCORING_TEMPLATE = """
You are an AI resume evaluator. Score the candidate based on the job criteria.

You will receive:
1. The parsed resume JSON
2. The job requirements text
3. A list of scoring criteria with weights

For each criteria:
{
    "criteriaId": <number>,
    "name": "<criteria description>",
    "weight": <0-1>
}

Return ONLY valid JSON with this format:
{
  "AIExplanation": "<overall explanation text>",
  "items": [
    {
      "criteriaId": <number>,
      "matched": <float 0-1>,
      "score": <0-100>,
      "AINote": "<short explanation>"
    }
  ],
  "total_score": <0-100>
}

Rules:
- matched: 0.0 to 1.0 similarity
- score: 0-100 relevance score
- total_score = sum(score[i] * weight[i])
- Do not generate markdown or comments
- Only count experience relevant to the field stated in the criteria.
- Never infer information not stated in the resume.
- Never give high score unless criteria are clearly satisfied.
- Explanation must be short and factual.
- DO NOT count unrelated experience (e.g., software engineering ≠ graphic design).
- If the candidate has no experience in the required field → matched = 0, score = 0.
- If the criteria specify “>= X months/years”:
    - Map only matching-field experience.
    - If less than required → matched proportional, but capped (never exceed requirement level).
    - If zero relevant experience → matched = 0.
""".strip()


def _truncate_requirements(requirements: str, max_length: int = MAX_REQUIREMENTS_LENGTH) -> str:
    """Truncate requirements text to a safe limit."""
    if len(requirements) <= max_length:
        return requirements
    logger.warning(
        "Requirements text truncated from %d to %d characters",
        len(requirements),
        max_length
    )
    return requirements[:max_length]


def _build_criteria_prompt(
    parsed_resume: Dict[str, Any],
    requirements: str,
    criteria_list: List[Dict[str, Any]]
) -> str:
    """Build the AI prompt for criteria-based scoring."""
    # Truncate requirements to prevent token limit issues
    truncated_requirements = _truncate_requirements(requirements)
    criteria_json = json.dumps(criteria_list, ensure_ascii=False)
    resume_json = json.dumps(parsed_resume, ensure_ascii=False)

    return (
        f"{CRITERIA_SCORING_TEMPLATE}\n\n"
        f"JOB REQUIREMENTS:\n{truncated_requirements}\n\n"
        f"SCORING CRITERIA:\n{criteria_json}\n\n"
        f"CANDIDATE RESUME DATA:\n{resume_json}"
    )


def _extract_gemini_response(response) -> str:
    """Extract text from Gemini response object."""
    if hasattr(response, "parts") and response.parts:
        return "".join(part.text for part in response.parts if getattr(part, "text", "")).strip()
    elif response.candidates:
        candidate = response.candidates[0]
        if candidate.content and candidate.content.parts:
            return "".join(part.text for part in candidate.content.parts if getattr(part, "text", "")).strip()
        else:
            raise AIScoringError("Gemini returned empty scoring response")
    else:
        raise AIScoringError("Gemini returned empty scoring response")


def _validate_ai_response_structure(result: Dict[str, Any]) -> None:
    """Validate that AI response has the required structure."""
    if "items" not in result:
        raise AIScoringError("Gemini response missing 'items' field")

    items = result["items"]
    if not isinstance(items, list):
        raise AIScoringError("Gemini response 'items' must be a list")

    required_fields = {"criteriaId", "matched", "score", "AINote"}
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise AIScoringError(f"Item at index {idx} is not a dictionary")

        missing_fields = required_fields - set(item.keys())
        if missing_fields:
            raise AIScoringError(
                f"Item at index {idx} missing required fields: {', '.join(missing_fields)}"
            )


def _normalize_ai_response(result: Dict[str, Any], criteria_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize AI response: ensure types and structure.

    Args:
        result: AI response dict
        criteria_list: List of criteria with weights to multiply scores
    """
    # Create a mapping of criteriaId to weight
    criteria_weights = {
        int(c["criteriaId"]): float(c.get("weight") or 0.0)
        for c in criteria_list
    }

    # Ensure AIExplanation is a string
    ai_explanation = result.get("AIExplanation", "")
    if isinstance(ai_explanation, dict):
        # Convert dict to string representation if needed
        ai_explanation = ai_explanation.strip('"')

    elif not isinstance(ai_explanation, str):
        ai_explanation = str(ai_explanation) if ai_explanation else ""

    result["AIExplanation"] = ai_explanation

    # Normalize items: force-cast criteriaId to int and multiply score by weight
    items = result.get("items", [])
    normalized_items = []
    for item in items:
        criteria_id = int(item.get("criteriaId", 0))
        raw_score = float(item.get("score", 0))
        weight = criteria_weights.get(criteria_id, 0.0)

        # Multiply score by weight before returning
        weighted_score = round(raw_score * weight, 2)

        normalized_item = {
            "criteriaId": criteria_id,
            "matched": float(item.get("matched", 0.0)),
            "score": weighted_score,  # Now this is score * weight
            "AINote": str(item.get("AINote", "")),
        }
        normalized_items.append(normalized_item)

    result["items"] = normalized_items
    return result


def _calculate_weighted_total_score(items: List[Dict[str, Any]]) -> float:
    """Calculate total score by summing pre-weighted scores.

    Note: Items already have scores multiplied by weights in _normalize_ai_response.
    """
    total = sum(float(item.get("score", 0)) for item in items)
    return round(total, 2)


def score_by_criteria(
    parsed_resume: Dict[str, Any],
    requirements: str,
    criteria_list: List[Dict[str, Any]],
    *,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Score the resume based on criteria list using Gemini.

    Args:
        parsed_resume: The parsed resume JSON
        requirements: The job requirements text
        criteria_list: List of criteria dicts with criteriaId, name, weight
        api_key: Optional Gemini API key

    Returns:
        Dict with AIExplanation, items (AIScoreDetail), and total_score
    """
    if not requirements:
        raise ValueError("Job requirements are required for scoring")
    if not criteria_list:
        raise ValueError("Criteria list is required for scoring")

    prompt = _build_criteria_prompt(parsed_resume, requirements, criteria_list)
    model = get_model(api_key=api_key)

    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,  # Deterministic scoring - same resume always gets same score
                max_output_tokens=8192,
            ),
        )
        raw_text = _extract_gemini_response(response)
        result = _clean_ai_response(raw_text)

        # Validate response structure
        _validate_ai_response_structure(result)

        # Normalize response (ensure types, multiply scores by weights)
        result = _normalize_ai_response(result, criteria_list)

        # Calculate total_score by summing pre-weighted scores
        items = result["items"]
        result["total_score"] = _calculate_weighted_total_score(items)

        return result
    except AIScoringError:
        raise
    except Exception as exc:
        raise AIScoringError("Failed to score resume with Gemini") from exc
