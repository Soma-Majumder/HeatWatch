"""All settings come from .env. Nothing here is hard-coded elsewhere in the app."""
import os

from dotenv import load_dotenv

load_dotenv()


def _float(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val else default


def _int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val else default


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = os.getenv("HEATWATCH_MODEL", "claude-haiku-4-5-20251001")

# Budgets per question run (CLAUDE.md hard rule #5)
COST_CAP_USD = _float("HEATWATCH_COST_CAP_USD", 0.25)
MAX_STEPS = _int("HEATWATCH_MAX_STEPS", 12)
MAX_QUERIES = _int("HEATWATCH_MAX_QUERIES", 8)
MAX_SKILL_LOADS = _int("HEATWATCH_MAX_SKILL_LOADS", 4)
MAX_SECONDS = _float("HEATWATCH_MAX_SECONDS", 120)

SOCRATA_BASE_URL = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
SOCRATA_APP_TOKEN = os.getenv("HEATWATCH_SOCRATA_APP_TOKEN", "")
SOCRATA_TIMEOUT_SECONDS = 20
SOCRATA_RETRYABLE_RETRIES = 1  # one retry after a 2s backoff, for transient 5xx only

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_TIMEOUT_SECONDS = 20
CENTRAL_PARK_LAT = 40.7829
CENTRAL_PARK_LON = -73.9654

# Subject facts (confirmed in spike/NOTES.md)
HEAT_SEASON_START = (10, 1)  # Oct 1
HEAT_SEASON_END = (5, 31)  # May 31
HDD_BASE_FAHRENHEIT = 65
SMALL_BASE_THRESHOLD = 20  # below this, percent change comes back null + flagged
POSSIBLY_INCOMPLETE_DAYS = 2  # a period ending this close to the latest record may still be filling in
