"""Settings. Values come from environment variables with plan defaults."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path(os.environ.get("HEATWATCH_DB", ROOT / "data" / "heatwatch.db"))
    # Saved 311 view: HEAT/HOT WATER, Manhattan Community Board 12 (Washington Heights/Inwood)
    source_url: str = os.environ.get(
        "HEATWATCH_SOURCE_URL", "https://data.cityofnewyork.us/resource/fbiz-gkhq.json"
    )
    window_days: int = int(os.environ.get("HEATWATCH_WINDOW_DAYS", "730"))  # rolling 2 years
    page_size: int = int(os.environ.get("HEATWATCH_PAGE_SIZE", "50000"))
    app_token: str | None = os.environ.get("SOCRATA_APP_TOKEN")
    # Plan decision 4 (default): 90-day retention for tenant-submitted data
    retention_days: int = int(os.environ.get("HEATWATCH_RETENTION_DAYS", "90"))


def get_settings() -> Settings:
    return Settings()
