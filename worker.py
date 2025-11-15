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
        email = info.get("email")
    
    # Extract phone (default None)
    phone_number = None
    if isinstance(info, dict):
        phone_number = info.get("phoneNumber") or info.get("phone") or info.get("contact")
    
    # Return with guaranteed fields (all default to None)
    return {
        "fullName": full_name,
        "email": email,
        "phoneNumber": phone_number,
    }


def _process_job(job: Dict[str, Any], client: CallbackClient, gemini_api_key: str) -> None:
    required_fields = ["resumeId", "queueJobId", "jobId", "fileUrl"]
    missing = [field for field in required_fields if field not in job]
    if missing:
        raise ValueError(f"Job missing required fields: {', '.join(missing)}")

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

    logger.info(
        "Starting job queueId=%s resumeId=%s jobId=%s",
        job["queueJobId"],
        job["resumeId"],
        job["jobId"],
    )

    file_path, should_cleanup = _download_file(job["fileUrl"])
    try:
        logger.debug("Downloaded resume to %s (cleanup=%s)",
                     file_path, should_cleanup)
        resume_text = extract_text_from_file(file_path)
        logger.info("Extracted resume text (%s chars)", len(resume_text))
        parsed_resume = ats_extractor(
            resume_text, api_key=gemini_api_key or None)
        logger.info("Parsed resume sections: %s", list(parsed_resume.keys()))
        
        # Score using criteria-based scoring
        scores = score_by_criteria(
            parsed_resume, requirements, criteria_list, api_key=gemini_api_key or None)
        logger.info(
            "Calculated scores for job queueId=%s (total=%s)",
            job["queueJobId"],
            scores.get("total_score"),
        )

        # Extract candidate info (guaranteed fields with None defaults)
        candidate_info = _extract_candidate_info(parsed_resume)
        
        # Get AIScoreDetail from AI response items ONLY (already normalized with int criteriaId)
        ai_score_detail = scores.get("items", [])
        
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
        client.send_ai_result(payload)
        logger.info(
            "Submitted AI results queueId=%s resumeId=%s",
            job["queueJobId"],
            job["resumeId"],
        )
    finally:
        if should_cleanup and file_path.exists():
            file_path.unlink()


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
