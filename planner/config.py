"""Configuration, read once from environment variables (and an optional .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional at runtime
    pass


def _list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.replace("\n", ",").split(",") if item.strip()]


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "ja"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw and raw.strip() else default


@dataclass
class Config:
    # General
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("Europe/Zurich"))
    language: str = "de"
    page_format: str = "remarkable"
    months_ahead: int = 3
    day_start_hour: int = 6
    day_end_hour: int = 22
    notes_pages: int = 10
    data_dir: Path = Path("/data")
    output_dir: Path = Path("/data/output")

    # Composio (Google Tasks, Google Calendar)
    composio_api_key: str | None = None
    composio_user_id: str | None = None
    composio_base_url: str = "https://backend.composio.dev/api/v3"
    composio_toolkit_version: str | None = None
    composio_tasks_account_id: str | None = None
    composio_calendar_account_id: str | None = None
    google_tasks_lists: list[str] = field(default_factory=list)  # names or IDs; empty = all
    google_calendar_ids: list[str] = field(default_factory=list)
    holiday_calendar_ids: list[str] = field(default_factory=list)

    # ICS feeds (iCloud, Outlook, Google secret address, holiday feeds ...)
    ics_urls: list[str] = field(default_factory=list)
    holiday_ics_urls: list[str] = field(default_factory=list)

    # Sync to the tablet
    sync_mode: str = "cloud"  # cloud | ssh | none
    remarkable_folder: str = "Kalender"
    rmapi_bin: str = "rmapi"
    rmapi_config: Path = Path("/data/rmapi.conf")
    rmapi_one_time_code: str | None = None
    remarkable_host: str | None = None
    remarkable_password: str | None = None

    # Scheduler / monitoring
    sync_times: list[str] = field(default_factory=lambda: ["04:30"])
    run_on_start: bool = True
    healthcheck_url: str | None = None

    @property
    def status_file(self) -> Path:
        return self.data_dir / "status.json"

    @property
    def composio_enabled(self) -> bool:
        return bool(self.composio_api_key and self.composio_user_id)


def load_config() -> Config:
    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    return Config(
        timezone=ZoneInfo(os.getenv("TZ", "Europe/Zurich") or "Europe/Zurich"),
        language=os.getenv("PLANNER_LANGUAGE", "de").lower(),
        page_format=os.getenv("PAGE_FORMAT", "remarkable").lower(),
        months_ahead=max(1, _int("MONTHS_AHEAD", 3)),
        day_start_hour=_int("DAY_START_HOUR", 6),
        day_end_hour=_int("DAY_END_HOUR", 22),
        notes_pages=_int("NOTES_PAGES", 10),
        data_dir=data_dir,
        output_dir=Path(os.getenv("OUTPUT_DIR", str(data_dir / "output"))),
        composio_api_key=os.getenv("COMPOSIO_API_KEY") or None,
        composio_user_id=os.getenv("COMPOSIO_USER_ID") or None,
        composio_base_url=os.getenv("COMPOSIO_BASE_URL", "https://backend.composio.dev/api/v3").rstrip("/"),
        composio_toolkit_version=os.getenv("COMPOSIO_TOOLKIT_VERSION") or None,
        composio_tasks_account_id=os.getenv("COMPOSIO_TASKS_ACCOUNT_ID") or None,
        composio_calendar_account_id=os.getenv("COMPOSIO_CALENDAR_ACCOUNT_ID") or None,
        google_tasks_lists=_list("GOOGLE_TASKS_LISTS"),
        google_calendar_ids=_list("GOOGLE_CALENDAR_IDS"),
        holiday_calendar_ids=_list("HOLIDAY_CALENDAR_IDS"),
        ics_urls=_list("ICS_URLS"),
        holiday_ics_urls=_list("HOLIDAY_ICS_URLS"),
        sync_mode=os.getenv("SYNC_MODE", "cloud").lower(),
        remarkable_folder=os.getenv("REMARKABLE_FOLDER", "Kalender").strip("/") or "Kalender",
        rmapi_bin=os.getenv("RMAPI_BIN", "rmapi"),
        rmapi_config=Path(os.getenv("RMAPI_CONFIG", str(data_dir / "rmapi.conf"))),
        rmapi_one_time_code=os.getenv("RMAPI_ONE_TIME_CODE") or None,
        remarkable_host=os.getenv("REMARKABLE_HOST") or None,
        remarkable_password=os.getenv("REMARKABLE_PASSWORD") or None,
        sync_times=_list("SYNC_TIMES") or ["04:30"],
        run_on_start=_bool("RUN_ON_START", True),
        healthcheck_url=os.getenv("HEALTHCHECK_URL") or None,
    )
