"""Client for communicating with the .NET backend."""

from __future__ import annotations

import logging
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)


class CallbackClient:
    """Wrapper around the backend HTTP APIs."""

    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.verify = False

    def send_ai_result(self, payload: Dict[str, Any]) -> None:
        url = f"{self.base_url}/api/resume/result"
        logger.info("Sending AI result payload to %s: %s", url, payload)
        response = self.session.post(url, json=payload, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            logger.error("Failed to send AI result for queue job %s: %s",
                         payload.get("queueJobId"), exc)
            raise

    def close(self) -> None:
        self.session.close()
