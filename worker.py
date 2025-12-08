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
from worker.services.scorer import score_by_criteria, score_by_criteria_advanced

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

JOB_QUEUE = "resume_parse_queue"
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
            raw_text = "".join(part.text for part in response.parts if getattr(part, "text", "")).strip()
        elif response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                raw_text = "".join(part.text for part in candidate.content.parts if getattr(part, "text", "")).strip()
            else:
                logger.warning("AI validation returned empty response, defaulting to False")
                return False
        else:
            logger.warning("AI validation returned empty response, defaulting to False")
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
            logger.info("AI validation result: is_resume=%s, reason=%s", is_resume, reason)
            return bool(is_resume)
        except json.JSONDecodeError:
            logger.warning("AI validation returned invalid JSON, defaulting to False")
            return False
            
    except Exception as exc:
        logger.warning("AI validation failed: %s, falling back to rule-based validation", exc)
        return None  # Signal to fall back to rule-based validation


def _looks_like_resume(parsed_resume: Dict[str, Any], resume_text: str | None = None, gemini_api_key: str | None = None) -> bool:
    """Validate if document is actually a resume using AI and rule-based checks."""

    if resume_text is not None and len(resume_text.strip()) < 50:
        # Almost no text extracted; likely not a resume
        logger.info("Resume text too short (%d chars), not a resume", len(resume_text.strip()))
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
            logger.info("Has basic info + 1 critical field, using AI validation")
            # Use AI validation as tie-breaker
            if resume_text and gemini_api_key:
                ai_result = _validate_resume_with_ai(resume_text, parsed_resume, gemini_api_key)
                if ai_result is not None:
                    return ai_result
            # If AI validation fails or not available, reject
            return False
        else:
            return False
    
    # If we have 2+ critical fields, use AI validation to double-check
    # (in case it's a novel that happens to have some structured data)
    if resume_text and gemini_api_key and len(resume_text) > 200:
        ai_result = _validate_resume_with_ai(resume_text, parsed_resume, gemini_api_key)
        if ai_result is not None:
            return ai_result
    
    # If we get here, rule-based validation passed
    logger.info("Resume validation passed: has %d critical fields", critical_fields_count)
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
            criteria_names = [c.get("name", "") for c in criteria_list if isinstance(c, dict)]
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
            raw_text = "".join(part.text for part in response.parts if getattr(part, "text", "")).strip()
        elif response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                raw_text = "".join(part.text for part in candidate.content.parts if getattr(part, "text", "")).strip()
            else:
                logger.warning("AI job validation returned empty response, defaulting to True")
                return True
        else:
            logger.warning("AI job validation returned empty response, defaulting to True")
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
            logger.info("AI job requirements validation: is_valid=%s, reason=%s", is_valid, reason)
            return bool(is_valid)
        except json.JSONDecodeError:
            logger.warning("AI job validation returned invalid JSON, defaulting to True")
            return True
            
    except Exception as exc:
        logger.warning("AI job requirements validation failed: %s, defaulting to True", exc)
        return True


def _send_invalid_resume_payload(job: Dict[str, Any], client: CallbackClient, error_type: str = "not_a_resume") -> None:
    """Send a minimal payload indicating an invalid upload or job data."""
    payload = {
        "queueJobId": str(job["queueJobId"]),
        "resumeId": int(job["resumeId"]),
        "jobId": int(job["jobId"]),
        "error": error_type,
    }

    logger.warning(
        "Detected invalid data (error=%s). Sending error payload queueId=%s resumeId=%s jobId=%s",
        error_type,
        job["queueJobId"],
        job["resumeId"],
        job["jobId"],
    )
    client.send_ai_result(payload)


def _process_job(job: Dict[str, Any], client: CallbackClient, gemini_api_key: str) -> None:
    # Get mode from job payload (default to "parse" for backward compatibility)
    mode = job.get("mode", "parse")
    
    # Validate required fields based on mode
    if mode == "rescore":
        required_fields = ["resumeId", "queueJobId", "jobId", "parsedData"]
    else:  # mode == "parse"
        required_fields = ["resumeId", "queueJobId", "jobId", "fileUrl"]
    
    missing = [field for field in required_fields if field not in job]
    if missing:
        raise ValueError(f"Job missing required fields for mode '{mode}': {', '.join(missing)}")

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
    job_specialization = job.get("specialization")  # job field/specialization name
    job_employment_types = job.get("employmentTypes")  # comma-separated employment types

    logger.info(
        "Starting job queueId=%s resumeId=%s jobId=%s mode=%s",
        job["queueJobId"],
        job["resumeId"],
        job["jobId"],
        mode,
    )
    if job_skills or job_specialization or job_employment_types:
        logger.info(
            "Job context: skills=%s, specialization=%s, employmentTypes=%s",
            job_skills[:50] if job_skills else None,
            job_specialization,
            job_employment_types,
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
        _send_invalid_resume_payload(job, client, "not_a_resume")
        return

    # =========================================================================
    # MODE: RESCORE - Use existing parsed data, advanced scoring only
    # =========================================================================
    if mode == "rescore":
        logger.info("Mode: RESCORE - Using pre-parsed data for advanced analysis")
        
        # Get parsed resume data from payload (sent by backend)
        parsed_resume = job["parsedData"]
        if not parsed_resume:
            raise ValueError("parsedData is empty for rescore mode")
        
        # Ensure parsed_resume is a dict
        if isinstance(parsed_resume, str):
            try:
                parsed_resume = json.loads(parsed_resume)
            except json.JSONDecodeError as exc:
                raise ValueError("Failed to parse parsedData JSON") from exc
        
        logger.info("Using pre-parsed resume data (keys: %s)", list(parsed_resume.keys()))
        
        # Score using ADVANCED criteria-based scoring
        scores = score_by_criteria_advanced(
            parsed_resume, requirements, criteria_list,
            api_key=gemini_api_key or None,
            skills=job_skills,
            specialization=job_specialization,
            employment_types=job_employment_types,
        )
        logger.info(
            "Advanced scoring completed for job queueId=%s (total=%s)",
            job["queueJobId"],
            scores.get("total_score"),
        )
        
        # Extract candidate info from existing parsed data
        candidate_info = _extract_candidate_info(parsed_resume)
        
        # Build payload - rawJson stays the same (no re-parsing)
        _send_result_payload(job, scores, parsed_resume, candidate_info, client)
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
            _send_invalid_resume_payload(job, client)
            return

        # Score using standard criteria-based scoring
        scores = score_by_criteria(
            parsed_resume, requirements, criteria_list,
            api_key=gemini_api_key or None,
            skills=job_skills,
            specialization=job_specialization,
            employment_types=job_employment_types,
        )
        logger.info(
            "Calculated scores for job queueId=%s (total=%s)",
            job["queueJobId"],
            scores.get("total_score"),
        )

        # Extract candidate info (guaranteed fields with None defaults)
        candidate_info = _extract_candidate_info(parsed_resume)

        # Build and send payload
        _send_result_payload(job, scores, parsed_resume, candidate_info, client)
    finally:
        if should_cleanup and file_path.exists():
            file_path.unlink()


def _send_result_payload(
    job: Dict[str, Any],
    scores: Dict[str, Any],
    parsed_resume: Dict[str, Any],
    candidate_info: Dict[str, Any],
    client: CallbackClient
) -> None:
    """Build and send the result payload to backend."""
    # Get AIScoreDetail from AI response items ONLY (already normalized with int criteriaId)
    ai_score_detail = scores.get("items", [])

    # Merge matchSkills and missingSkills from AI scoring into candidate_info
    candidate_info["matchSkills"] = scores.get("matchSkills")
    candidate_info["missingSkills"] = scores.get("missingSkills")

    # Ensure AIExplanation is a string (already normalized in scorer)
    ai_explanation = scores.get("AIExplanation", "")
    if not isinstance(ai_explanation, str):
        ai_explanation = str(ai_explanation) if ai_explanation else ""

    # Build payload exactly as .NET expects
    payload = {
        "queueJobId": str(job["queueJobId"]),
        "resumeId": int(job["resumeId"]),
        "jobId": int(job["jobId"]),
        "totalResumeScore": float(scores.get("total_score", 0)),
        "AIExplanation": ai_explanation,
        "AIScoreDetail": ai_score_detail,
        "rawJson": parsed_resume,
        "candidateInfo": candidate_info,
    }

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
    logger.info("  • jobId: %s (value: %s)", type(
        payload["jobId"]).__name__, payload["jobId"])
    logger.info("  • totalResumeScore: %s (value: %s)", type(
        payload["totalResumeScore"]).__name__, payload["totalResumeScore"])
    logger.info("  • AIExplanation: %s (length: %s)", type(
        payload["AIExplanation"]).__name__, len(payload["AIExplanation"]))
    logger.info("  • AIScoreDetail: %s (count: %s)", type(
        payload["AIScoreDetail"]).__name__, len(payload["AIScoreDetail"]))
    logger.info("  • rawJson: %s (keys: %s)", type(payload["rawJson"]).__name__, list(
        payload["rawJson"].keys()) if isinstance(payload["rawJson"], dict) else "N/A")
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

    logger.info("AI Resume Worker started. Listening on queue '%s'", JOB_QUEUE)

    while True:
        try:
            _, raw_job = redis_conn.blpop(JOB_QUEUE)
        except Exception as exc:  # pragma: no cover - redis network failures
            logger.error("Redis BLPOP failed: %s", exc)
            time.sleep(RETRY_DELAY_SECONDS)
            continue

        try:
            job = _parse_job(raw_job)
            logger.info("Dequeued job queueId=%s", job.get("queueJobId"))
        except ValueError as exc:
            logger.error("Dropping invalid job payload: %s", exc)
            continue

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                _process_job(job, callback_client, settings.gemini_api_key)
                break
            except Exception as exc:
                logger.exception(
                    "Failed to process job %s (attempt %s/%s)",
                    job.get("queueJobId"),
                    attempt,
                    MAX_RETRIES,
                )
                if attempt >= MAX_RETRIES:
                    logger.error("Giving up on job %s after %s attempts", job.get(
                        "queueJobId"), MAX_RETRIES)
                else:
                    time.sleep(RETRY_DELAY_SECONDS * attempt)


def main() -> None:
    worker_loop()


if __name__ == "__main__":
    main()
