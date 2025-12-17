"""Redis-backed AI resume worker."""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Tuple
from urllib.parse import urlparse

import requests

from callback_client import CallbackClient
from config import load_settings
from redis_client import get_redis_connection
from worker.services.file_reader import extract_text_from_file
from worker.services.parser import ats_extractor
from worker.services.scorer import score_by_criteria
from worker.services.comparator import compare_candidates

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)


JOB_QUEUE = "resume_parse_queue"
COMPARISON_QUEUE = "candidate_comparison_queue"
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5


def _download_file(file_url: str) -> Tuple[Path, bool]:
    """Download a remote file or reuse a local path.

    Returns a tuple of (path, should_cleanup).
    """

    if file_url.startswith(("http://", "https://")):
        parsed = urlparse(file_url)
        suffix = Path(parsed.path).suffix or ".dat"
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            response = requests.get(file_url, stream=True, timeout=60)
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
        return Path(temp_file.name), True
    else:
        path = Path(file_url).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Resume file not found: {file_url}")
        return path, False


def _parse_job(raw_job: bytes) -> Dict[str, Any]:
    try:
        return json.loads(raw_job.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid job payload received from Redis") from exc


def _extract_candidate_info(parsed_resume: Dict[str, Any]) -> Dict[str, Any]:
    """Extract candidate info from parsed resume.

    Looks for possible keys:
    - name, fullName
    - email
    - phone, phoneNumber, contact

    Returns a dict with guaranteed fields (defaults to None).
    """
    info = parsed_resume.get("info", {})

    # Handle case where info might be a string (JSON string)
    if isinstance(info, str):
        try:
            info = json.loads(info)
        except (json.JSONDecodeError, TypeError):
            info = {}

    # Extract name (default None)
    full_name = None
    if isinstance(info, dict):
        full_name = info.get("fullName") or info.get("name")

    # Extract email (default None)
    email = None
    if isinstance(info, dict):
        # Check if email is directly in info
        email = info.get("email")
        # If not, check in contact object
        if not email and isinstance(info.get("contact"), dict):
            email = info["contact"].get("email")

    # Extract phone (default None)
    phone_number = None
    if isinstance(info, dict):
        # Check direct fields first
        phone_number = info.get("phoneNumber") or info.get("phone")
        # If not found, check in contact object
        if not phone_number and isinstance(info.get("contact"), dict):
            contact = info["contact"]
            phone_number = contact.get("phone") or contact.get(
                "phoneNumber") or contact.get("contact")

    # Return with guaranteed fields (all default to None or string type)
    return {
        "fullName": full_name,
        "email": email,
        "phoneNumber": phone_number,
        "matchSkills": None,  # Will be populated from AI scoring
        "missingSkills": None,  # Will be populated from AI scoring
    }


def _validate_resume_with_ai(resume_text: str, parsed_resume: Dict[str, Any], api_key: str | None = None) -> bool:
    """Use AI to validate if the document is actually a resume."""
    try:
        from worker.services.gemini_client import get_model
        import google.generativeai as genai

        model = get_model(api_key=api_key)

        # Create a compact summary of parsed data for AI validation
        parsed_summary = {
            "has_work_experience": bool(parsed_resume.get("work_experience")),
            "has_education": bool(parsed_resume.get("education")),
            "has_skills": bool(parsed_resume.get("technical_skills")),
            "has_basic_info": bool(parsed_resume.get("info", {}).get("fullName") or
                                   parsed_resume.get("info", {}).get("email")),
            "text_length": len(resume_text),
        }

        validation_prompt = f"""You are a document classifier. Determine if the following document is a RESUME/CV or NOT a resume.

Document text (first 2000 chars): {resume_text[:2000]}

Parsed structure summary: {json.dumps(parsed_summary, ensure_ascii=False)}

Respond with ONLY a JSON object:
{{
    "is_resume": true or false,
    "reason": "brief explanation"
}}

A resume/CV should contain:
- Professional work experience OR education history
- Contact information (name, email, phone)
- Skills, certifications, or projects related to professional qualifications

A novel, story, article, or other non-resume document should return false."""

        response = model.generate_content(
            validation_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,
                max_output_tokens=512,
            ),
        )

        # Extract response text
        if hasattr(response, "parts") and response.parts:
            raw_text = "".join(part.text for part in response.parts if getattr(
                part, "text", "")).strip()
        elif response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                raw_text = "".join(part.text for part in candidate.content.parts if getattr(
                    part, "text", "")).strip()
            else:
                logger.warning(
                    "AI validation returned empty response, defaulting to False")
                return False
        else:
            logger.warning(
                "AI validation returned empty response, defaulting to False")
            return False

        # Clean and parse JSON response
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            result = json.loads(cleaned)
            is_resume = result.get("is_resume", False)
            reason = result.get("reason", "")
            logger.info(
                "AI validation result: is_resume=%s, reason=%s", is_resume, reason)
            return bool(is_resume)
        except json.JSONDecodeError:
            logger.warning(
                "AI validation returned invalid JSON, defaulting to False")
            return False

    except Exception as exc:
        logger.warning(
            "AI validation failed: %s, falling back to rule-based validation", exc)
        return None  # Signal to fall back to rule-based validation


def _looks_like_resume(parsed_resume: Dict[str, Any], resume_text: str | None = None, gemini_api_key: str | None = None) -> bool:
    """Validate if document is actually a resume using AI and rule-based checks."""

    if resume_text is not None and len(resume_text.strip()) < 50:
        # Almost no text extracted; likely not a resume
        logger.info("Resume text too short (%d chars), not a resume",
                    len(resume_text.strip()))
        return False

    if not isinstance(parsed_resume, dict):
        return False

    info = parsed_resume.get("info") or {}
    if isinstance(info, str):
        try:
            info = json.loads(info)
        except (TypeError, json.JSONDecodeError):
            info = {}

    # Check basic contact info
    has_basic_info = False
    if isinstance(info, dict):
        has_name = bool(info.get("fullName") or info.get("name"))
        has_email = bool(info.get("email"))
        has_phone = bool(info.get("phone") or info.get("phoneNumber"))
        has_basic_info = has_name or (has_email and has_phone)

    def _list_has_content(value: Any) -> bool:
        if not value:
            return False
        if not isinstance(value, list):
            return False
        # Check if list has at least one item with actual content
        for item in value:
            if isinstance(item, dict):
                # Check if dict has at least one non-empty string value
                if any(v for v in item.values() if isinstance(v, str) and v.strip()):
                    return True
            elif isinstance(item, str) and item.strip():
                return True
        return False

    has_experience = _list_has_content(parsed_resume.get("work_experience"))
    has_education = _list_has_content(parsed_resume.get("education"))

    tech_skills = parsed_resume.get("technical_skills")
    has_skills = False
    if isinstance(tech_skills, dict):
        has_skills = any(
            bool(value) and isinstance(value, list) and len(value) > 0
            for value in tech_skills.values()
            if value is not None
        )

    # STRICT VALIDATION: Must have at least 2 of the 3 critical fields
    critical_fields_count = sum([has_experience, has_education, has_skills])

    # Rule 1: Must have at least 2 critical fields (experience, education, or skills)
    if critical_fields_count < 2:
        logger.info(
            "Resume validation failed: only %d critical fields found (need 2+). "
            "has_experience=%s, has_education=%s, has_skills=%s",
            critical_fields_count, has_experience, has_education, has_skills
        )

        # Rule 2: Fallback - if has basic info AND at least 1 critical field, might be valid
        if has_basic_info and critical_fields_count >= 1:
            logger.info(
                "Has basic info + 1 critical field, using AI validation")
            # Use AI validation as tie-breaker
            if resume_text and gemini_api_key:
                ai_result = _validate_resume_with_ai(
                    resume_text, parsed_resume, gemini_api_key)
                if ai_result is not None:
                    return ai_result
            # If AI validation fails or not available, reject
            return False
        else:
            return False

    # If we have 2+ critical fields, use AI validation to double-check
    # (in case it's a novel that happens to have some structured data)
    if resume_text and gemini_api_key and len(resume_text) > 200:
        ai_result = _validate_resume_with_ai(
            resume_text, parsed_resume, gemini_api_key)
        if ai_result is not None:
            return ai_result

    # If we get here, rule-based validation passed
    logger.info("Resume validation passed: has %d critical fields",
                critical_fields_count)
    return True


def _validate_job_requirements_with_ai(requirements: str, criteria_list: list, api_key: str | None = None) -> bool:
    """Use AI to validate if requirements and criteria are meaningful job descriptions."""
    try:
        from worker.services.gemini_client import get_model
        import google.generativeai as genai

        model = get_model(api_key=api_key)

        # Build criteria text for validation
        criteria_text = ""
        if criteria_list:
            criteria_names = [c.get("name", "")
                              for c in criteria_list if isinstance(c, dict)]
            criteria_text = ", ".join(criteria_names)

        validation_prompt = f"""You are a job posting validator. Determine if the following job requirements and criteria are MEANINGFUL and VALID for recruitment purposes.

Job Requirements (first 1000 chars):
{requirements[:1000]}

Criteria Names:
{criteria_text[:500]}

Respond with ONLY a JSON object:
{{
    "is_valid": true or false,
    "reason": "brief explanation"
}}

VALID job requirements should:
- Describe actual job responsibilities, skills needed, or qualifications
- Be written in a coherent, professional manner
- Make sense as part of a real job posting

INVALID job requirements (return false):
- Random/gibberish text like "jkjfsalhfsfsjfsjflsfjj" or "asdfasdf"
- Repeated meaningless words like "requirement requirement requirement"
- Text that doesn't describe any actual job duties or qualifications
- Lorem ipsum or placeholder text
- Nonsensical combinations of characters

Be STRICT: If the text looks like random typing, testing, or placeholder content, return false."""

        response = model.generate_content(
            validation_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,
                max_output_tokens=256,
            ),
        )

        # Extract response text
        if hasattr(response, "parts") and response.parts:
            raw_text = "".join(part.text for part in response.parts if getattr(
                part, "text", "")).strip()
        elif response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                raw_text = "".join(part.text for part in candidate.content.parts if getattr(
                    part, "text", "")).strip()
            else:
                logger.warning(
                    "AI job validation returned empty response, defaulting to True")
                return True
        else:
            logger.warning(
                "AI job validation returned empty response, defaulting to True")
            return True

        # Clean and parse JSON response
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            result = json.loads(cleaned)
            is_valid = result.get("is_valid", True)
            reason = result.get("reason", "")
            logger.info(
                "AI job requirements validation: is_valid=%s, reason=%s", is_valid, reason)
            return bool(is_valid)
        except json.JSONDecodeError:
            logger.warning(
                "AI job validation returned invalid JSON, defaulting to True")
            return True

    except Exception as exc:
        logger.warning(
            "AI job requirements validation failed: %s, defaulting to True", exc)
        return True


# ============================================================================
# JOB TITLE MATCHING - Use AI to validate candidate's job title matches
# ============================================================================


def _extract_titles_from_resume(parsed_resume: Dict[str, Any]) -> list[str]:
    """Extract all job-related titles from parsed resume."""
    titles = []

    # Extract from work experience titles
    work_exp = parsed_resume.get("work_experience", [])
    if isinstance(work_exp, list):
        for exp in work_exp:
            if isinstance(exp, dict):
                title = exp.get("title") or exp.get(
                    "position") or exp.get("job_title")
                if title and isinstance(title, str):
                    titles.append(title.strip())
                # Also get company for context
                company = exp.get("company")
                if company and title:
                    titles.append(f"{title.strip()} at {company}")

    # Extract from summary/headline
    summary = parsed_resume.get("summary")
    if summary and isinstance(summary, str):
        titles.append(summary.strip())

    # Extract from info section (headline, title, etc.)
    info = parsed_resume.get("info", {})
    if isinstance(info, dict):
        headline = info.get("headline") or info.get(
            "title") or info.get("professional_title")
        if headline and isinstance(headline, str):
            titles.append(headline.strip())

    return titles


def _validate_job_title_match(job_title: str, parsed_resume: Dict[str, Any], api_key: str | None = None) -> Dict[str, Any]:
    """Validate if candidate's experience matches the required job title using AI.

    Returns:
        Dict with:
        - matched: bool - True if job title matches
        - reason: str - Explanation of the match/mismatch
    """
    # Default response for error cases
    default_error_response = {
        "matched": False,
        "reason": "Unable to validate job title"
    }

    if not job_title or not job_title.strip():
        # No job title specified, skip validation (consider as matched)
        logger.info("No job title specified, skipping job title validation")
        return {
            "matched": True,
            "reason": "No job title requirement specified"
        }

    resume_titles = _extract_titles_from_resume(parsed_resume)

    if not resume_titles:
        logger.warning("No job titles found in resume for matching")
        return {
            "matched": False,
            "reason": "No job titles or work experience found in resume"
        }

    logger.info("Validating job title '%s' against resume titles: %s",
                job_title, resume_titles[:5])

    if not api_key:
        logger.warning("No API key provided for job title validation")
        return default_error_response

    try:
        from worker.services.gemini_client import get_model
        import google.generativeai as genai

        model = get_model(api_key=api_key)

        validation_prompt = f"""You are a job title matcher for recruitment. Determine if the candidate's experience matches the required job title.

REQUIRED JOB TITLE: {job_title}

CANDIDATE'S TITLES/EXPERIENCE FROM RESUME:
{chr(10).join(f'- {t}' for t in resume_titles[:15])}

MATCHING RULES:
1. Focus on the CORE FUNCTION of the job, not exact title match
2. Similar roles should match:
   - "Software Engineer" ≈ "Software Developer" ≈ "Programmer"
   - "Backend Developer" ≈ "Backend Engineer" ≈ "Server-side Developer"
   - "Frontend Developer" ≈ "UI Developer" ≈ "Web Developer"
   - "Data Analyst" ≈ "Business Analyst" ≈ "BI Analyst"
   - "AI Engineer" ≈ "Machine Learning Engineer" ≈ "ML Engineer"
3. More senior roles can match junior requirements (Senior Developer → Developer)
4. Related technology stack indicates match (e.g., "React Developer" matches "Frontend Developer")
5. Don't match completely unrelated fields (e.g., "Cook" ≠ "Software Developer")

Respond with ONLY a JSON object:
{{
    "matched": true or false,
    "reason": "Brief explanation of why it matches or doesn't match"
}}

Examples:
- Required: "Backend Developer", Resume has "Software Engineer - Backend" → {{"matched": true, "reason": "Applicant was 'Software Engineer - Backend' which is equivalent to 'Backend Developer'"}}
- Required: "Data Analyst", Resume has "Marketing Manager" → {{"matched": false, "reason": "No data analysis or analytics experience found in resume"}}
- Required: "Frontend Developer", Resume has "React Developer" → {{"matched": true, "reason": "React Developer is a specialized frontend role"}}"""

        response = model.generate_content(
            validation_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,
                max_output_tokens=256,
            ),
        )

        # Extract response
        if hasattr(response, "parts") and response.parts:
            raw_text = "".join(part.text for part in response.parts if getattr(
                part, "text", "")).strip()
        elif response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                raw_text = "".join(part.text for part in candidate.content.parts if getattr(
                    part, "text", "")).strip()
            else:
                logger.warning(
                    "AI job title validation returned empty response")
                return default_error_response
        else:
            logger.warning("AI job title validation returned empty response")
            return default_error_response

        # Clean and parse JSON
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        result = json.loads(cleaned)
        matched = result.get("matched", False)
        reason = result.get("reason", "")

        logger.info(
            "AI job title validation: matched=%s, reason=%s", matched, reason)

        return {
            "matched": bool(matched),
            "reason": str(reason) if reason else ("Job title matches" if matched else "Job title does not match")
        }

    except json.JSONDecodeError as exc:
        logger.warning(
            "AI job title validation returned invalid JSON: %s", exc)
        return default_error_response
    except Exception as exc:
        logger.warning("AI job title validation failed: %s", exc)
        return default_error_response


def _send_invalid_resume_payload(
    job: Dict[str, Any],
    client: CallbackClient,
    error_type: str = "not_a_resume",
    reason: str | None = None
) -> None:
    """Send a minimal payload indicating an invalid upload or job data."""
    payload = {
        "queueJobId": str(job["queueJobId"]),
        "resumeId": int(job["resumeId"]),
        "applicationId": int(job["applicationId"]),
        "jobId": int(job["jobId"]),
        "campaignId": int(job["campaignId"]),
        "companyId": int(job["companyId"]),
        "error": error_type,
    }

    # Add reason if provided (for job_title_not_matched error)
    if reason:
        payload["reason"] = reason

    logger.warning(
        "Detected invalid data (error=%s, reason=%s). Sending error payload queueId=%s resumeId=%s applicationId=%s jobId=%s campaignId=%s companyId=%s",
        error_type,
        reason,
        job["queueJobId"],
        job["resumeId"],
        job["applicationId"],
        job["jobId"],
        job["campaignId"],
        job["companyId"],
    )
    client.send_ai_result(payload)


def _process_job(job: Dict[str, Any], client: CallbackClient, gemini_api_key: str) -> None:
    # Get mode from job payload (default to "parse" for backward compatibility)
    mode = job.get("mode", "parse")

    # Validate required fields based on mode
    if mode == "score":
        required_fields = ["resumeId", "applicationId", "queueJobId",
                           "jobId", "campaignId", "companyId", "parsedData"]
    else:  # mode == "parse" (default)
        required_fields = ["resumeId", "applicationId", "queueJobId",
                           "jobId", "campaignId", "companyId", "fileUrl"]

    missing = [field for field in required_fields if field not in job]
    if missing:
        raise ValueError(
            f"Job missing required fields for mode '{mode}': {', '.join(missing)}")

    # Validate requirements and criteria from Redis payload
    if "requirements" not in job:
        logger.error(
            "Job missing 'requirements' field. Skipping job queueId=%s resumeId=%s jobId=%s",
            job.get("queueJobId"),
            job.get("resumeId"),
            job.get("jobId"),
        )
        raise ValueError("Job missing 'requirements' field")

    if "criteria" not in job:
        logger.error(
            "Job missing 'criteria' field. Skipping job queueId=%s resumeId=%s jobId=%s",
            job.get("queueJobId"),
            job.get("resumeId"),
            job.get("jobId"),
        )
        raise ValueError("Job missing 'criteria' field")

    requirements = job["requirements"]
    criteria_list = job["criteria"]

    if not requirements:
        logger.error(
            "Job 'requirements' is empty. Skipping job queueId=%s resumeId=%s jobId=%s",
            job.get("queueJobId"),
            job.get("resumeId"),
            job.get("jobId"),
        )
        raise ValueError("Job 'requirements' is empty")

    if not criteria_list or not isinstance(criteria_list, list):
        logger.error(
            "Job 'criteria' is empty or invalid. Skipping job queueId=%s resumeId=%s jobId=%s",
            job.get("queueJobId"),
            job.get("resumeId"),
            job.get("jobId"),
        )
        raise ValueError("Job 'criteria' is empty or invalid")

    # Extract optional job context fields (new fields from backend)
    job_skills = job.get("skills")  # comma-separated skills list
    # job field/specialization name
    job_specialization = job.get("specialization")
    # comma-separated employment types
    job_employment_types = job.get("employmentTypes")
    # comma-separated languages to recruit
    job_languages = job.get("languages")
    job_level = job.get("level")  # job level (intern, junior, senior, etc.)
    job_title = job.get("jobTitle")  # job title for matching validation

    logger.info(
        "Starting job queueId=%s resumeId=%s jobId=%s mode=%s",
        job["queueJobId"],
        job["resumeId"],
        job["jobId"],
        mode,
    )
    if job_skills or job_specialization or job_employment_types or job_languages or job_level or job_title:
        logger.info(
            "Job context: title=%s, skills=%s, specialization=%s, employmentTypes=%s, languages=%s, level=%s",
            job_title,
            job_skills[:50] if job_skills else None,
            job_specialization,
            job_employment_types,
            job_languages,
            job_level,
        )

    # =========================================================================
    # VALIDATE JOB REQUIREMENTS AND CRITERIA ARE MEANINGFUL
    # =========================================================================
    if not _validate_job_requirements_with_ai(requirements, criteria_list, gemini_api_key):
        logger.warning(
            "Invalid/meaningless job requirements detected for queueId=%s resumeId=%s jobId=%s",
            job["queueJobId"],
            job["resumeId"],
            job["jobId"],
        )
        _send_invalid_resume_payload(job, client, "invalid_job_data")
        return

    # =========================================================================
    # MODE: SCORE - Use existing parsed data, scoring only (no parsing)
    # =========================================================================
    if mode == "score":
        logger.info(
            "Mode: SCORE - Using pre-parsed data for scoring only")

        # Get parsed resume data from payload (sent by backend)
        parsed_resume = job["parsedData"]
        if not parsed_resume:
            raise ValueError("parsedData is empty for score mode")

        # Ensure parsed_resume is a dict
        if isinstance(parsed_resume, str):
            try:
                parsed_resume = json.loads(parsed_resume)
            except json.JSONDecodeError as exc:
                raise ValueError("Failed to parse parsedData JSON") from exc

        logger.info("Using pre-parsed resume data (keys: %s)",
                    list(parsed_resume.keys()))

        # =====================================================================
        # VALIDATE JOB TITLE MATCHING (if jobTitle is provided)
        # =====================================================================
        if job_title:
            title_match_result = _validate_job_title_match(
                job_title, parsed_resume, gemini_api_key)
            if not title_match_result.get("matched", False):
                logger.warning(
                    "Job title mismatch for queueId=%s resumeId=%s jobId=%s (required: %s, reason: %s)",
                    job["queueJobId"],
                    job["resumeId"],
                    job["jobId"],
                    job_title,
                    title_match_result.get("reason", "Unknown"),
                )
                _send_invalid_resume_payload(
                    job, client, "job_title_not_matched",
                    reason=title_match_result.get("reason")
                )
                return

        # Score using standard criteria-based scoring
        scores = score_by_criteria(
            parsed_resume, requirements, criteria_list,
            api_key=gemini_api_key or None,
            skills=job_skills,
            specialization=job_specialization,
            employment_types=job_employment_types,
            languages=job_languages,
            level=job_level,
        )
        logger.info(
            "Scoring completed for job queueId=%s (total=%s)",
            job["queueJobId"],
            scores.get("total_score"),
        )

        # Extract candidate info from existing parsed data
        candidate_info = _extract_candidate_info(parsed_resume)

        # Build payload WITHOUT rawJson (resume already in database)
        _send_result_payload(job, scores, None,
                             candidate_info, client, mode="score")
        return

    # =========================================================================
    # MODE: PARSE - Download file, parse resume, then score (default flow)
    # =========================================================================
    logger.info("Mode: PARSE - Downloading and parsing resume file")

    file_path, should_cleanup = _download_file(job["fileUrl"])
    try:
        logger.debug("Downloaded resume to %s (cleanup=%s)",
                     file_path, should_cleanup)
        resume_text = extract_text_from_file(file_path)
        logger.info("Extracted resume text (%s chars)", len(resume_text))
        parsed_resume = ats_extractor(
            resume_text, api_key=gemini_api_key or None)
        logger.info("Parsed resume sections: %s", list(parsed_resume.keys()))

        if not _looks_like_resume(parsed_resume, resume_text, gemini_api_key):
            _send_invalid_resume_payload(job, client, "invalid_resume_data")
            return

        # =====================================================================
        # VALIDATE JOB TITLE MATCHING (if jobTitle is provided)
        # =====================================================================
        if job_title:
            title_match_result = _validate_job_title_match(
                job_title, parsed_resume, gemini_api_key)
            if not title_match_result.get("matched", False):
                logger.warning(
                    "Job title mismatch for queueId=%s resumeId=%s jobId=%s (required: %s, reason: %s)",
                    job["queueJobId"],
                    job["resumeId"],
                    job["jobId"],
                    job_title,
                    title_match_result.get("reason", "Unknown"),
                )
                _send_invalid_resume_payload(
                    job, client, "job_title_not_matched",
                    reason=title_match_result.get("reason")
                )
                return

        # Score using standard criteria-based scoring
        scores = score_by_criteria(
            parsed_resume, requirements, criteria_list,
            api_key=gemini_api_key or None,
            skills=job_skills,
            specialization=job_specialization,
            employment_types=job_employment_types,
            languages=job_languages,
            level=job_level,
        )
        logger.info(
            "Calculated scores for job queueId=%s (total=%s)",
            job["queueJobId"],
            scores.get("total_score"),
        )

        # Extract candidate info (guaranteed fields with None defaults)
        candidate_info = _extract_candidate_info(parsed_resume)

        # Build and send payload with rawJson
        _send_result_payload(job, scores, parsed_resume,
                             candidate_info, client, mode="parse")
    finally:
        if should_cleanup and file_path.exists():
            file_path.unlink()


def _build_require_skills(match_skills: str | None, missing_skills: str | None) -> str | None:
    """Build requireSkills string from matchSkills and missingSkills.

    requireSkills = matchSkills + missingSkills (combined, unique skills)
    """
    parts = []

    # Parse matchSkills if provided
    if match_skills and isinstance(match_skills, str) and match_skills.strip():
        # Split by comma and add to parts
        match_list = [s.strip() for s in match_skills.split(",") if s.strip()]
        parts.extend(match_list)

    # Parse missingSkills if provided
    if missing_skills and isinstance(missing_skills, str) and missing_skills.strip():
        # Split by comma and add to parts
        missing_list = [s.strip()
                        for s in missing_skills.split(",") if s.strip()]
        parts.extend(missing_list)

    # Remove duplicates while preserving order
    seen = set()
    unique_parts = []
    for part in parts:
        if part.lower() not in seen:  # Case-insensitive deduplication
            seen.add(part.lower())
            unique_parts.append(part)

    if unique_parts:
        return ", ".join(unique_parts)
    return None


def _send_result_payload(
    job: Dict[str, Any],
    scores: Dict[str, Any],
    parsed_resume: Dict[str, Any] | None,
    candidate_info: Dict[str, Any],
    client: CallbackClient,
    mode: str = "parse"
) -> None:
    """Build and send the result payload to backend.

    Args:
        job: Job data from Redis
        scores: Scoring results
        parsed_resume: Parsed resume JSON (None for score mode)
        candidate_info: Candidate information
        client: Callback client
        mode: Processing mode ("parse" or "score")
    """
    # Get AIScoreDetail from AI response items ONLY (already normalized with int criteriaId)
    ai_score_detail = scores.get("items", [])

    # Get matchSkills and missingSkills from AI scoring
    match_skills = scores.get("matchSkills")
    missing_skills = scores.get("missingSkills")

    # Merge matchSkills and missingSkills from AI scoring into candidate_info
    candidate_info["matchSkills"] = match_skills
    candidate_info["missingSkills"] = missing_skills

    # Ensure AIExplanation is a string (already normalized in scorer)
    ai_explanation = scores.get("AIExplanation", "")
    if not isinstance(ai_explanation, str):
        ai_explanation = str(ai_explanation) if ai_explanation else ""

    # Build requireSkills from matchSkills + missingSkills
    require_skills = _build_require_skills(match_skills, missing_skills)

    # Build payload exactly as .NET expects
    payload = {
        "queueJobId": str(job["queueJobId"]),
        "resumeId": int(job["resumeId"]),
        "applicationId": int(job["applicationId"]),
        "jobId": int(job["jobId"]),
        "campaignId": int(job["campaignId"]),
        "companyId": int(job["companyId"]),
        "totalResumeScore": float(scores.get("total_score", 0)),
        "AIExplanation": ai_explanation,
        "AIScoreDetail": ai_score_detail,
        "requireSkills": require_skills,
        "candidateInfo": candidate_info,
    }

    # Include rawJson only for parse mode (not for score mode)
    if mode == "parse" and parsed_resume is not None:
        payload["rawJson"] = parsed_resume

    # === DETAILED PAYLOAD VALIDATION & LOGGING ===
    logger.info("=" * 80)
    logger.info("🔍 PAYLOAD VALIDATION BEFORE SENDING")
    logger.info("=" * 80)

    # Log data types
    logger.info("📊 Data Types:")
    logger.info("  • queueJobId: %s (value: %s)", type(
        payload["queueJobId"]).__name__, payload["queueJobId"])
    logger.info("  • resumeId: %s (value: %s)", type(
        payload["resumeId"]).__name__, payload["resumeId"])
    logger.info("  • applicationId: %s (value: %s)", type(
        payload["applicationId"]).__name__, payload["applicationId"])
    logger.info("  • jobId: %s (value: %s)", type(
        payload["jobId"]).__name__, payload["jobId"])
    logger.info("  • campaignId: %s (value: %s)", type(
        payload["campaignId"]).__name__, payload["campaignId"])
    logger.info("  • companyId: %s (value: %s)", type(
        payload["companyId"]).__name__, payload["companyId"])
    logger.info("  • totalResumeScore: %s (value: %s)", type(
        payload["totalResumeScore"]).__name__, payload["totalResumeScore"])
    logger.info("  • AIExplanation: %s (length: %s)", type(
        payload["AIExplanation"]).__name__, len(payload["AIExplanation"]))
    logger.info("  • AIScoreDetail: %s (count: %s)", type(
        payload["AIScoreDetail"]).__name__, len(payload["AIScoreDetail"]))

    # Log rawJson only if present (parse mode)
    if "rawJson" in payload:
        logger.info("  • rawJson: %s (keys: %s)", type(payload["rawJson"]).__name__, list(
            payload["rawJson"].keys()) if isinstance(payload["rawJson"], dict) else "N/A")
    else:
        logger.info("  • rawJson: NOT INCLUDED (score mode)")

    logger.info("  • requireSkills: %s (value: %s)", type(
        payload["requireSkills"]).__name__ if payload["requireSkills"] else "NoneType",
        payload["requireSkills"][:100] if payload["requireSkills"] else None)
    logger.info("  • candidateInfo: %s", type(
        payload["candidateInfo"]).__name__)

    # Log candidateInfo details
    logger.info("👤 Candidate Info:")
    for key, value in candidate_info.items():
        logger.info("  • %s: %s (type: %s)", key,
                    value, type(value).__name__)

    # Validate AIScoreDetail is not empty
    if not ai_score_detail:
        logger.warning("⚠️ WARNING: AIScoreDetail is EMPTY!")
    else:
        logger.info("✅ AIScoreDetail has %s items", len(ai_score_detail))
        # Log first item as sample
        if ai_score_detail:
            logger.info("📋 Sample AIScoreDetail item:")
            sample = ai_score_detail[0]
            logger.info("  %s", json.dumps(sample, indent=4))

    # Validate score range
    if not (0 <= payload["totalResumeScore"] <= 100):
        logger.warning(
            "⚠️ WARNING: totalResumeScore out of range [0-100]: %s", payload["totalResumeScore"])

    # Validate AIExplanation
    if not payload["AIExplanation"]:
        logger.warning("⚠️ WARNING: AIExplanation is empty!")

    logger.info("=" * 80)

    client.send_ai_result(payload)
    logger.info(
        "Submitted AI results queueId=%s resumeId=%s",
        job["queueJobId"],
        job["resumeId"],
    )


def _process_comparison_job(job: Dict[str, Any], client: CallbackClient, gemini_api_key: str) -> None:
    """Process a candidate comparison job from Redis queue.

    Args:
        job: Comparison job data from Redis
        client: Callback client for sending results
        gemini_api_key: Gemini API key for AI processing
    """
    # Validate required fields
    required_fields = ["comparisonId", "queueJobId", "companyId", "campaignId",
                       "jobId", "jobTitle", "requirements", "criteria", "candidates"]

    missing = [field for field in required_fields if field not in job]
    if missing:
        raise ValueError(
            f"Comparison job missing required fields: {', '.join(missing)}")

    comparison_id = job["comparisonId"]
    queue_job_id = job["queueJobId"]
    company_id = job["companyId"]
    campaign_id = job["campaignId"]
    job_id = job["jobId"]

    logger.info(
        "Starting comparison job comparisonId=%s queueJobId=%s jobId=%s candidates=%d",
        comparison_id,
        queue_job_id,
        job_id,
        len(job.get("candidates", [])),
    )

    # Validate candidates count
    candidates = job.get("candidates", [])
    if len(candidates) < 2:
        logger.error(
            "Insufficient candidates for comparison (minimum 2 required, got %d)", len(candidates))
        _send_comparison_error_payload(
            job, client,
            error="insufficient_candidates",
            reason=f"Not enough candidates for comparison (minimum 2 required, got {len(candidates)})"
        )
        return

    if len(candidates) > 5:
        logger.error(
            "Too many candidates for comparison (maximum 5 allowed, got %d)", len(candidates))
        _send_comparison_error_payload(
            job, client,
            error="invalid_data",
            reason=f"Too many candidates for comparison (maximum 5 allowed, got {len(candidates)})"
        )
        return

    try:
        # Call comparison service
        result = compare_candidates(job, api_key=gemini_api_key)

        # Check if comparison returned error
        if result.get("status") == "error":
            logger.error(
                "Comparison failed for comparisonId=%s: %s - %s",
                comparison_id,
                result.get("error"),
                result.get("reason"),
            )
            _send_comparison_error_payload(
                job, client,
                error=result.get("error", "processing_failed"),
                reason=result.get("reason", "Unknown error during comparison")
            )
            return

        # Build success payload
        payload = {
            "queueJobId": str(queue_job_id),
            "comparisonId": int(comparison_id),
            "campaignId": int(campaign_id),
            "jobId": int(job_id),
            "companyId": int(company_id),
            "resultJson": result,
        }

        logger.info(
            "✅ Comparison completed successfully for comparisonId=%s with %d candidates",
            comparison_id,
            len(result.get("candidates", [])),
        )

        # Send result to backend
        client.send_comparison_result(payload)
        logger.info(
            "Submitted comparison results comparisonId=%s queueJobId=%s",
            comparison_id,
            queue_job_id,
        )

    except Exception as exc:
        logger.exception(
            "Error processing comparison job comparisonId=%s: %s",
            comparison_id,
            exc,
        )
        _send_comparison_error_payload(
            job, client,
            error="processing_failed",
            reason=f"Internal error: {str(exc)}"
        )


def _send_comparison_error_payload(
    job: Dict[str, Any],
    client: CallbackClient,
    error: str,
    reason: str
) -> None:
    """Send an error payload for comparison job.

    Args:
        job: Job data from Redis
        client: Callback client
        error: Error code
        reason: Error reason/message
    """
    payload = {
        "queueJobId": str(job["queueJobId"]),
        "comparisonId": int(job["comparisonId"]),
        "campaignId": int(job["campaignId"]),
        "jobId": int(job["jobId"]),
        "companyId": int(job["companyId"]),
        "error": error,
        "reason": reason,
    }

    logger.warning(
        "Sending comparison error payload: comparisonId=%s error=%s reason=%s",
        job["comparisonId"],
        error,
        reason,
    )

    client.send_comparison_result(payload)


def worker_loop() -> None:
    settings = load_settings()
    logger.info("Loaded settings: redis=%s backend=%s",
                settings.redis_url, settings.backend_api_url)
    redis_conn = get_redis_connection(settings.redis_url)
    logger.info("Connected to Redis at %s", settings.redis_url)
    callback_client = CallbackClient(settings.backend_api_url)

    def _graceful_shutdown(signum: int, frame: Any) -> None:  # pragma: no cover - signal handling
        logger.info("Received signal %s, shutting down worker", signum)
        callback_client.close()
        redis_conn.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    logger.info("Commit 1")
    logger.info(
        "AI Resume Worker started. Listening on queues: ['%s', '%s']", JOB_QUEUE, COMPARISON_QUEUE)

    while True:
        try:
            # BLPOP can monitor multiple queues - returns (queue_name, data)
            queue_name, raw_job = redis_conn.blpop(
                [JOB_QUEUE, COMPARISON_QUEUE])
            queue_name = queue_name.decode(
                "utf-8") if isinstance(queue_name, bytes) else queue_name
        except Exception as exc:  # pragma: no cover - redis network failures
            logger.error("Redis BLPOP failed: %s", exc)
            time.sleep(RETRY_DELAY_SECONDS)
            continue

        try:
            job = _parse_job(raw_job)
            logger.info("Dequeued job from queue '%s' queueId=%s",
                        queue_name, job.get("queueJobId"))
        except ValueError as exc:
            logger.error(
                "Dropping invalid job payload from queue '%s': %s", queue_name, exc)
            continue

        # Route to appropriate processor based on queue
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if queue_name == COMPARISON_QUEUE:
                    logger.info(
                        "Processing comparison job (attempt %s/%s)", attempt, MAX_RETRIES)
                    _process_comparison_job(
                        job, callback_client, settings.gemini_api_key)
                else:  # JOB_QUEUE (resume parsing/scoring)
                    logger.info(
                        "Processing resume job (attempt %s/%s)", attempt, MAX_RETRIES)
                    _process_job(job, callback_client, settings.gemini_api_key)
                break
            except Exception as exc:
                logger.exception(
                    "Failed to process job from queue '%s' %s (attempt %s/%s)",
                    queue_name,
                    job.get("queueJobId"),
                    attempt,
                    MAX_RETRIES,
                )
                if attempt >= MAX_RETRIES:
                    logger.error("Giving up on job %s from queue '%s' after %s attempts",
                                 job.get("queueJobId"), queue_name, MAX_RETRIES)
                else:
                    time.sleep(RETRY_DELAY_SECONDS * attempt)


def main() -> None:
    worker_loop()


if __name__ == "__main__":
    main()
