"""admin_web configuration — separate from backend/core/config.py and the
root config/settings.py; this process only ever talks to the backend over
HTTP, so its only real setting is where that backend lives."""

from __future__ import annotations

import os

BACKEND_URL = os.environ.get("ADMIN_WEB_BACKEND_URL", "http://localhost:8000")
