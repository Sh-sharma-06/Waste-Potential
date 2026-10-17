"""Environment configuration for Waste-Potential."""

import os
from pathlib import Path

from dotenv import load_dotenv

# backend/app/config.py -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def get_setting(name: str, default: str = "") -> str:
    """Read a setting without exposing its value in logs."""
    return os.getenv(name, default).strip()


GEMINI_MODEL = get_setting("GEMINI_MODEL", "gemini-2.5-flash")

GEMINI_API_KEY_AUDIT = get_setting("GEMINI_API_KEY_AUDIT")
GEMINI_API_KEY_ADVISOR = get_setting("GEMINI_API_KEY_ADVISOR")
GEMINI_API_KEY_PARSER = get_setting("GEMINI_API_KEY_PARSER")