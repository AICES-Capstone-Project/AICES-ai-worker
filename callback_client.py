"""Client for communicating with the .NET backend."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)


class CallbackClient:
    """Client for sending AI results back to backend API."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.result_url = f"{self.base_url}/api/resume/result/ai"  # Add this line
        self.session = requests.Session()
        logger.info("Initialized callback client with URL: %s",
                    self.result_url)

    def send_ai_result(self, payload: Dict[str, Any]) -> None:
        """Send AI parsing results back to backend API."""
        logger.info("=" * 80)
        logger.info("🚀 SENDING PAYLOAD TO BACKEND API")
        logger.info("=" * 80)
        # Change from self._result_url
        logger.info("📍 Target URL: %s", self.result_url)

        # Log full payload with pretty formatting
        try:
            formatted_payload = json.dumps(
                payload, indent=2, ensure_ascii=False)
            logger.info("📦 Full Payload:\n%s", formatted_payload)
        except Exception as e:
            logger.warning("⚠️ Could not format payload as JSON: %s", e)
            logger.info("📦 Raw Payload: %s", payload)

        logger.info("=" * 80)

        try:
            logger.info("🔄 Making POST request...")
            response = self.session.post(
                # Change from self._result_url
                self.result_url, json=payload, timeout=30, verify=False
            )

            logger.info("📡 Response Status Code: %s", response.status_code)

            if response.status_code != 200:
                logger.error("=" * 80)
                logger.error("❌ ERROR RESPONSE FROM BACKEND")
                logger.error("=" * 80)
                logger.error("Status Code: %s", response.status_code)
                logger.error("Response Headers: %s", dict(response.headers))
                try:
                    logger.error("Response Body:\n%s", response.text)
                except Exception as e:
                    logger.error("Could not read response body: %s", e)
                logger.error("=" * 80)
            else:
                logger.info("✅ Successfully sent AI result")
                try:
                    # First 500 chars
                    logger.info("Response Body: %s", response.text[:500])
                except Exception:
                    pass

            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            logger.error("=" * 80)
            logger.error("💥 EXCEPTION DURING API CALL")
            logger.error("=" * 80)
            logger.error("Exception Type: %s", type(exc).__name__)
            logger.error("Exception Message: %s", exc)
            logger.error("=" * 80)
            raise
        except Exception as exc:
            logger.error("=" * 80)
            logger.error("💥 EXCEPTION DURING API CALL")
            logger.error("=" * 80)
            logger.error("Exception Type: %s", type(exc).__name__)
            logger.error("Exception Message: %s", exc)
            logger.error("=" * 80)
            raise

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.session.close()  # Change from self._session
        logger.info("Closed callback client session")
