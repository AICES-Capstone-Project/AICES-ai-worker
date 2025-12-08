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


# ============================================================================
# FIX #1: Cross-language + Anti-hallucination prompt
# FIX #2: Criteria name → Resume field mapping
# FIX #4: Remove contradictory instructions
# ============================================================================

CRITERIA_SCORING_TEMPLATE = """
You are an AI resume evaluator. Score the candidate based on the job criteria.

════════════════════════════════════════════════════════════════════════════════
🔥 CRITICAL: CROSS-LANGUAGE EVALUATION RULES (READ CAREFULLY!)
════════════════════════════════════════════════════════════════════════════════

The JOB REQUIREMENTS and CRITERIA may be in a different language than the RESUME.
For example: Requirements in Vietnamese, Resume in English (or vice versa).

⚠️ YOU MUST:
1. UNDERSTAND requirements in ANY language (Vietnamese, English, Japanese, etc.)
2. EVALUATE the resume based on its ACTUAL CONTENT (regardless of language)
3. NEVER translate or hallucinate resume content
4. MATCH semantic meaning across languages:
   - "Kinh nghiệm" (Vietnamese) = "Experience" = "work_experience" field
   - "Học vấn" (Vietnamese) = "Education" = "education" field
   - "Kỹ năng" (Vietnamese) = "Skills" = "technical_skills" field
   - "Chứng chỉ" (Vietnamese) = "Certifications" = "certifications" field
   - "Dự án" (Vietnamese) = "Projects" = "projects" field

════════════════════════════════════════════════════════════════════════════════
📋 CRITERIA NAME → RESUME FIELD MAPPING TABLE
════════════════════════════════════════════════════════════════════════════════

When evaluating criteria, map the criteria name to these resume JSON fields:

| Criteria Keywords (any language)      | Resume JSON Field(s) to Check       |
|--------------------------------------|-------------------------------------|
| Experience, Kinh nghiệm, 経験         | work_experience                     |
| Education, Học vấn, 学歴              | education                           |
| Skills, Kỹ năng, スキル               | technical_skills, languages_and_skills |
| Certifications, Chứng chỉ, 資格       | certifications                      |
| Projects, Dự án, プロジェクト          | projects                            |
| Languages, Ngôn ngữ, 言語             | languages_and_skills                |
| Personal Info, Thông tin cá nhân     | info                                |

════════════════════════════════════════════════════════════════════════════════

You will receive:
1. The parsed resume JSON (with standardized field names in English)
2. The job requirements text (may be in any language)
3. A list of scoring criteria with weights (may be in any language)

For each criteria:
{
    "criteriaId": <number>,
    "name": "<criteria description - may be in any language>",
    "weight": <0-1>
}

Return ONLY valid JSON with this format:
{
  "AIExplanation": "<overall explanation - ALWAYS USE ENGLISH for consistency>",
  "items": [
    {
      "criteriaId": <number>,
      "matched": <float 0-1>,
      "rawScore": <0.0-100.0 with decimals, e.g. 72.5, 45.3 - DO NOT multiply by weight>,
      "AINote": "<explanation citing specific resume content - ALWAYS USE ENGLISH>"
    }
  ],
  "matchSkills": "<comma-separated list of skills from resume that match job requirements>",
  "missingSkills": "<comma-separated list of required skills NOT found in resume>"
}

⚠️ IMPORTANT: DO NOT include "total_score" or "score" in your response.
The system will calculate weighted scores automatically using: rawScore * weight

════════════════════════════════════════════════════════════════════════════════
📏 SCORING RULES (STRICT - NO HALLUCINATION ALLOWED)
════════════════════════════════════════════════════════════════════════════════

1. MATCHED VALUE (0.0 - 1.0):
   - 0.0 = No match at all
   - 0.5 = Partial match
   - 1.0 = Perfect match
2. RAW SCORE (0.0 - 100.0) - UNWEIGHTED, USE DECIMALS:
   - Return the RAW score WITHOUT multiplying by weight
   - The system will apply weights automatically
   - USE DECIMAL VALUES (e.g., 72.5, 45.3, 88.7) for precision
   - AVOID round numbers like 50, 75, 80 - be specific!
   - Score ranges:
     * 0-20: No relevant content found in resume
     * 21-40: Minimal match
     * 41-60: Partial match
     * 61-80: Good match
     * 81-100: Excellent match (requires clear evidence)
   - Example precise scores: 23.5, 47.2, 68.8, 91.3

3. EXPERIENCE EVALUATION:
   - Only count experience relevant to the field stated in the criteria
   - DO NOT count unrelated experience (e.g., software engineering ≠ graphic design)
   - If candidate has no experience in required field → matched = 0, rawScore = 0
   - If criteria specify ">= X months/years":
     - Map only matching-field experience
     - If less than required → rawScore proportional (e.g., 2/3 years = 66)
     - If zero relevant experience → matched = 0, rawScore = 0

4. STRICT ANTI-HALLUCINATION RULES:
   - ONLY use information EXPLICITLY stated in the resume
   - NEVER infer, assume, or fabricate information
   - If information is missing → score it as missing (low score)
   - ALWAYS cite specific resume content in AINote as evidence
   - Keep explanations SHORT and FACTUAL (2-3 sentences max)
   - Do not generate markdown or comments
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


def _build_job_context_section(
    skills: Optional[str] = None,
    specialization: Optional[str] = None,
    employment_types: Optional[str] = None
) -> str:
    """Build job context section for the prompt."""
    context_parts = []
    
    if specialization:
        context_parts.append(f"• Job Specialization/Field: {specialization}")
    if skills:
        context_parts.append(f"• Required Skills: {skills}")
    if employment_types:
        context_parts.append(f"• Employment Type: {employment_types}")
    
    if context_parts:
        return "JOB CONTEXT:\n" + "\n".join(context_parts) + "\n\n"
    return ""


def _build_criteria_prompt(
    parsed_resume: Dict[str, Any],
    requirements: str,
    criteria_list: List[Dict[str, Any]],
    skills: Optional[str] = None,
    specialization: Optional[str] = None,
    employment_types: Optional[str] = None
) -> str:
    """Build the AI prompt for criteria-based scoring."""
    # Truncate requirements to prevent token limit issues
    truncated_requirements = _truncate_requirements(requirements)
    criteria_json = json.dumps(criteria_list, ensure_ascii=False)
    resume_json = json.dumps(parsed_resume, ensure_ascii=False)
    
    # Build job context section
    job_context = _build_job_context_section(skills, specialization, employment_types)

    return (
        f"{CRITERIA_SCORING_TEMPLATE}\n\n"
        f"{job_context}"
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

    # Accept either "rawScore" or "score" for backward compatibility
    required_fields = {"criteriaId", "matched", "AINote"}
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise AIScoringError(f"Item at index {idx} is not a dictionary")

        missing_fields = required_fields - set(item.keys())
        if missing_fields:
            raise AIScoringError(
                f"Item at index {idx} missing required fields: {', '.join(missing_fields)}"
            )
        
        # Must have either rawScore or score
        if "rawScore" not in item and "score" not in item:
            raise AIScoringError(
                f"Item at index {idx} missing 'rawScore' or 'score' field"
            )


# ============================================================================
# FIX #3: Fix double-weight calculation bug
# ============================================================================

def _normalize_ai_response(result: Dict[str, Any], criteria_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize AI response: ensure types and calculate weighted scores.

    FIXED: Now correctly applies weights ONCE (not twice).
    
    Args:
        result: AI response dict (with rawScore per item)
        criteria_list: List of criteria with weights
    
    Returns:
        Normalized result with weighted scores in 'score' field
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
        ai_explanation = str(ai_explanation)
    elif not isinstance(ai_explanation, str):
        ai_explanation = str(ai_explanation) if ai_explanation else ""

    result["AIExplanation"] = ai_explanation

    # Normalize items: apply weight to rawScore to get final score
    items = result.get("items", [])
    normalized_items = []
    for item in items:
        criteria_id = int(item.get("criteriaId", 0))
        
        # Get raw score (prefer rawScore, fall back to score for backward compat)
        raw_score = float(item.get("rawScore") or item.get("score") or 0)
        
        # Clamp raw_score to 0-100 range
        raw_score = max(0.0, min(100.0, raw_score))
        
        weight = criteria_weights.get(criteria_id, 0.0)

        # Calculate weighted score: rawScore * weight
        # This is the ONLY place where weight is applied
        weighted_score = round(raw_score * weight, 2)

        normalized_item = {
            "criteriaId": criteria_id,
            "matched": float(item.get("matched", 0.0)),
            "rawScore": raw_score,  # Keep original raw score for reference
            "score": weighted_score,  # This is rawScore * weight
            "AINote": str(item.get("AINote", "")),
        }
        normalized_items.append(normalized_item)

    result["items"] = normalized_items

    # Normalize matchSkills and missingSkills (ensure they are strings or None)
    match_skills = result.get("matchSkills")
    if match_skills is not None and not isinstance(match_skills, str):
        match_skills = str(match_skills)
    result["matchSkills"] = match_skills

    missing_skills = result.get("missingSkills")
    if missing_skills is not None and not isinstance(missing_skills, str):
        missing_skills = str(missing_skills)
    result["missingSkills"] = missing_skills

    return result


def _calculate_weighted_total_score(items: List[Dict[str, Any]]) -> float:
    """Calculate total score by summing pre-weighted scores.

    Note: Items already have weighted scores in 'score' field from _normalize_ai_response.
    Total = sum of all (rawScore * weight) values
    """
    total = sum(float(item.get("score", 0)) for item in items)
    # Clamp to 0-100 range (though it should naturally be within range if weights sum to 1)
    total = max(0.0, min(100.0, total))
    return round(total, 2)


def score_by_criteria(
    parsed_resume: Dict[str, Any],
    requirements: str,
    criteria_list: List[Dict[str, Any]],
    *,
    api_key: Optional[str] = None,
    skills: Optional[str] = None,
    specialization: Optional[str] = None,
    employment_types: Optional[str] = None,
) -> Dict[str, Any]:
    """Score the resume based on criteria list using Gemini.

    Args:
        parsed_resume: The parsed resume JSON
        requirements: The job requirements text
        criteria_list: List of criteria dicts with criteriaId, name, weight
        api_key: Optional Gemini API key
        skills: Optional comma-separated list of required skills
        specialization: Optional job specialization/field name
        employment_types: Optional comma-separated list of employment types

    Returns:
        Dict with AIExplanation, items (AIScoreDetail), and total_score
    """
    if not requirements:
        raise ValueError("Job requirements are required for scoring")
    if not criteria_list:
        raise ValueError("Criteria list is required for scoring")

    prompt = _build_criteria_prompt(
        parsed_resume, requirements, criteria_list,
        skills=skills, specialization=specialization, employment_types=employment_types
    )
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

        # Normalize response (ensure types, apply weights to get final scores)
        result = _normalize_ai_response(result, criteria_list)

        # Calculate total_score by summing weighted scores
        items = result["items"]
        result["total_score"] = _calculate_weighted_total_score(items)

        return result
    except AIScoringError:
        raise
    except Exception as exc:
        raise AIScoringError("Failed to score resume with Gemini") from exc


# ============================================================================
# ADVANCED SCORING (for rescore mode)
# ============================================================================

ADVANCED_SCORING_TEMPLATE = """
You are an EXPERT AI resume evaluator performing ADVANCED ANALYSIS.
This is a RE-SCORING request - the resume has already been parsed.
Perform DEEPER, MORE THOROUGH analysis than a standard first-pass evaluation.

════════════════════════════════════════════════════════════════════════════════
🔥 CRITICAL: CROSS-LANGUAGE EVALUATION RULES
════════════════════════════════════════════════════════════════════════════════

The JOB REQUIREMENTS and CRITERIA may be in a different language than the RESUME.
For example: Requirements in Vietnamese, Resume in English.

⚠️ YOU MUST:
1. UNDERSTAND requirements in ANY language (Vietnamese, English, Japanese, etc.)
2. EVALUATE the resume based on its ACTUAL CONTENT (regardless of language)
3. NEVER translate or hallucinate resume content
4. OUTPUT all explanations in ENGLISH for consistency
5. MATCH semantic meaning across languages:
   - "Kinh nghiệm" (Vietnamese) = "Experience" = work_experience field
   - "Học vấn" (Vietnamese) = "Education" = education field
   - "Kỹ năng" (Vietnamese) = "Skills" = technical_skills field

════════════════════════════════════════════════════════════════════════════════
📋 CRITERIA NAME → RESUME FIELD MAPPING TABLE
════════════════════════════════════════════════════════════════════════════════

| Criteria Keywords (any language)      | Resume JSON Field(s) to Check       |
|--------------------------------------|-------------------------------------|
| Experience, Kinh nghiệm, 経験         | work_experience                     |
| Education, Học vấn, 学歴              | education                           |
| Skills, Kỹ năng, スキル               | technical_skills, languages_and_skills |
| Certifications, Chứng chỉ, 資格       | certifications                      |
| Projects, Dự án, プロジェクト          | projects                            |

════════════════════════════════════════════════════════════════════════════════

You will receive:
1. The parsed resume JSON (already extracted data)
2. The job requirements text (may be in any language)
3. A list of scoring criteria with weights (may be in any language)

For each criteria:
{
    "criteriaId": <number>,
    "name": "<criteria description>",
    "weight": <0-1>
}

Return ONLY valid JSON with this format:
{
  "AIExplanation": "<comprehensive analysis - ALWAYS USE ENGLISH>",
  "items": [
    {
      "criteriaId": <number>,
      "matched": <float 0-1>,
      "rawScore": <0.0-100.0 with decimals, e.g. 73.5, 88.2 - DO NOT multiply by weight>,
      "AINote": "<detailed explanation citing resume content - ALWAYS USE ENGLISH>"
    }
  ],
  "matchSkills": "<comma-separated list of skills from resume that match job requirements>",
  "missingSkills": "<comma-separated list of required skills NOT found in resume>"
}

⚠️ IMPORTANT: DO NOT include "total_score" in your response.
The system will calculate: total_score = sum(rawScore[i] * weight[i])

════════════════════════════════════════════════════════════════════════════════
ADVANCED ANALYSIS GUIDELINES
════════════════════════════════════════════════════════════════════════════════

1. EXPERIENCE DEPTH ANALYSIS:
   - Calculate TOTAL years in the relevant field (sum all related positions)
   - Count ONLY experience directly relevant to the criteria field
   - Software engineering ≠ graphic design ≠ marketing ≠ sales
   - Junior roles ≠ Senior roles (weigh leadership/complexity differently)
   - Internships count as 0.5x weight unless full-time equivalent
   - Recent experience (last 2-3 years) weighs MORE than older experience

2. CAREER PROGRESSION ANALYSIS:
   + POSITIVE: Clear upward trajectory (Junior → Mid → Senior → Lead)
   + POSITIVE: Increasing responsibilities over time
   - NEGATIVE: Lateral moves without growth
   - NEGATIVE: Stuck at same level for 5+ years

3. EMPLOYMENT STABILITY:
   ✓ STABLE: Average tenure 2+ years per company
   ⚠ CAUTION: Average tenure 1-2 years
   ✗ UNSTABLE: Average tenure <1 year (red flag)
   
   Employment Gaps:
   - Gap < 3 months: Normal (ignore)
   - Gap 3-6 months: Note but don't penalize heavily
   - Gap > 6 months: Significant, reduce score if unexplained

4. SKILLS MATCHING (STRICT):
   - Required skills must be EXPLICITLY mentioned in resume
   - Consider recency: skills from 5+ years ago may be outdated

5. QUALITY INDICATORS (BOOST SCORE):
   + Quantified achievements (%, $, metrics)
   + Leadership experience (managed X people)
   + Impact statements (improved by X%)

6. RED FLAGS (REDUCE SCORE):
   - Employment gaps > 6 months without explanation
   - Frequent job changes (<1 year average)
   - Vague descriptions without specifics
   - Missing key required skills

════════════════════════════════════════════════════════════════════════════════
OUTPUT REQUIREMENTS
════════════════════════════════════════════════════════════════════════════════

AIExplanation MUST be DETAILED (200-400 words) and include these sections:

1. 📊 OVERALL FIT ASSESSMENT
   - How well does candidate match the job? (Poor/Fair/Good/Excellent)
   - Overall recommendation (Recommend/Consider/Not Recommend)

2. ✅ KEY STRENGTHS (list 3-5 points)
   - What makes this candidate stand out?
   - Relevant skills and experience highlights

3. ⚠️ KEY CONCERNS/GAPS (list 2-4 points)
   - Missing requirements or skills
   - Experience gaps or weaknesses

4. 📈 CAREER TRAJECTORY SUMMARY
   - Career progression pattern (growing/stable/declining)
   - Total relevant experience duration
   - Job stability assessment

5. 💡 FINAL VERDICT
   - One paragraph summary of candidate suitability
   - What role level they're best suited for (junior/mid/senior)

AINote per criteria MUST include:
- Specific evidence from resume (quote or cite)
- Why this score was given (factual reasoning)
- Any concerns for this specific criteria

SCORING PRECISION RULES:
- rawScore MUST use decimal values (e.g., 72.5, 45.3, 88.7)
- AVOID round numbers like 50, 75, 80 - be SPECIFIC!
- Base score on precise evaluation of resume evidence
- Example: 3.5 years experience for 5 year requirement → rawScore: 71.4 (not 70)

STRICT RULES:
- Be factual - cite specific resume content
- NEVER infer unstated information
- NEVER give high scores without clear evidence
- All output MUST be in ENGLISH
""".strip()


def _build_advanced_prompt(
    parsed_resume: Dict[str, Any],
    requirements: str,
    criteria_list: List[Dict[str, Any]],
    skills: Optional[str] = None,
    specialization: Optional[str] = None,
    employment_types: Optional[str] = None
) -> str:
    """Build the AI prompt for advanced criteria-based scoring."""
    truncated_requirements = _truncate_requirements(requirements)
    criteria_json = json.dumps(criteria_list, ensure_ascii=False)
    resume_json = json.dumps(parsed_resume, ensure_ascii=False)
    
    # Build job context section
    job_context = _build_job_context_section(skills, specialization, employment_types)

    return (
        f"{ADVANCED_SCORING_TEMPLATE}\n\n"
        f"{job_context}"
        f"JOB REQUIREMENTS:\n{truncated_requirements}\n\n"
        f"SCORING CRITERIA:\n{criteria_json}\n\n"
        f"CANDIDATE RESUME DATA (PRE-PARSED):\n{resume_json}"
    )


def score_by_criteria_advanced(
    parsed_resume: Dict[str, Any],
    requirements: str,
    criteria_list: List[Dict[str, Any]],
    *,
    api_key: Optional[str] = None,
    skills: Optional[str] = None,
    specialization: Optional[str] = None,
    employment_types: Optional[str] = None,
) -> Dict[str, Any]:
    """Advanced scoring for rescore mode - deeper analysis without re-parsing.

    This function performs more thorough evaluation with stricter criteria
    and more detailed explanations. Used when user requests re-scoring
    of an already-parsed resume.

    Args:
        parsed_resume: The pre-parsed resume JSON (from database)
        requirements: The job requirements text
        criteria_list: List of criteria dicts with criteriaId, name, weight
        api_key: Optional Gemini API key
        skills: Optional comma-separated list of required skills
        specialization: Optional job specialization/field name
        employment_types: Optional comma-separated list of employment types

    Returns:
        Dict with AIExplanation, items (AIScoreDetail), and total_score
    """
    if not requirements:
        raise ValueError("Job requirements are required for scoring")
    if not criteria_list:
        raise ValueError("Criteria list is required for scoring")
    if not parsed_resume:
        raise ValueError("Parsed resume data is required for advanced scoring")

    logger.info("Starting advanced scoring (rescore mode)")
    prompt = _build_advanced_prompt(
        parsed_resume, requirements, criteria_list,
        skills=skills, specialization=specialization, employment_types=employment_types
    )
    model = get_model(api_key=api_key)

    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,  # Slightly higher for more detailed analysis, but still deterministic
                max_output_tokens=8192,
            ),
        )
        raw_text = _extract_gemini_response(response)
        result = _clean_ai_response(raw_text)

        # Validate response structure
        _validate_ai_response_structure(result)

        # Normalize response (ensure types, apply weights to get final scores)
        result = _normalize_ai_response(result, criteria_list)

        # Calculate total_score by summing weighted scores
        items = result["items"]
        result["total_score"] = _calculate_weighted_total_score(items)

        logger.info("Advanced scoring completed (total_score=%s)", result["total_score"])
        return result
    except AIScoringError:
        raise
    except Exception as exc:
        raise AIScoringError("Failed to perform advanced scoring with Gemini") from exc
