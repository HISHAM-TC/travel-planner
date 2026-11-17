from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from app.config import API_RETRIES, API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


def request_json(url: str, *, user_agent: str = "TravelPlannerAgent/1.0") -> tuple[Any | None, str | None]:
    """Fetch JSON with bounded retries; return an explicit error on failure."""
    last_error = "request failed"
    for attempt in range(API_RETRIES + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": user_agent})
            with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8")), None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            logger.warning("HTTP JSON request failed (attempt %s/%s): %s", attempt + 1, API_RETRIES + 1, exc)
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}: {exc.reason}"
            exc.close()
            logger.warning("HTTP JSON request failed (attempt %s/%s): %s", attempt + 1, API_RETRIES + 1, last_error)
            if 400 <= exc.code < 500 and exc.code != 429:
                break

        if attempt < API_RETRIES:
            time.sleep(min(0.25 * (2**attempt), 1.0))
    return None, last_error
