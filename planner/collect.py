"""Load all events and tasks for a date range once, then group them by day in the planner timezone."""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from .config import Config
from .models import Event, Task

log = logging.getLogger(__name__)


def _norm(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


@dataclass
class PlannerData:
    today: date
    events: list[Event] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self):
        self._by_day: dict[date, list[Event]] = defaultdict(list)
        for ev in self.events:
            for d in ev.days():
                self._by_day[d].append(ev)
        for evs in self._by_day.values():
            evs.sort(key=lambda e: (not e.all_day, e.start if not e.all_day else e.start))

        self._tasks_by_day: dict[date, list[Task]] = defaultdict(list)
        for t in self.tasks:
            if t.due is None:
                continue
            if not t.completed and t.due < self.today:
                # Open tasks from the past move to today, like in Google Tasks.
                moved = Task(**{**t.__dict__, "overdue": True})
                self._tasks_by_day[self.today].append(moved)
            else:
                self._tasks_by_day[t.due].append(t)

    def events_on(self, d: date) -> list[Event]:
        return list(self._by_day.get(d, []))

    def tasks_on(self, d: date) -> list[Task]:
        titles = {_norm(e.title) for e in self._by_day.get(d, [])}
        tasks = [t for t in self._tasks_by_day.get(d, []) if _norm(t.title) not in titles]
        return sorted(tasks, key=lambda t: (t.completed, not t.overdue, t.list_name, t.title.lower()))

    def headlines_on(self, d: date) -> list[str]:
        items = [e.display for e in self._by_day.get(d, [])
                 if e.holiday or e.headline]
        items += [t.display for t in self._tasks_by_day.get(d, []) if t.headline and not t.overdue]
        return items

    def headline_map(self, year: int) -> dict[date, list[str]]:
        result: dict[date, list[str]] = {}
        for d in list(self._by_day) + list(self._tasks_by_day):
            if d.year == year and d not in result:
                items = self.headlines_on(d)
                if items:
                    result[d] = items
        return result


def build_sources(cfg: Config):
    from .sources.composio import ComposioClient
    from .sources.google_calendar import GoogleCalendarSource
    from .sources.google_tasks import GoogleTasksSource
    from .sources.ics import IcsSource

    event_sources, task_sources = [], []
    if cfg.composio_enabled:
        client = ComposioClient(cfg.composio_api_key, cfg.composio_user_id, cfg.composio_base_url,
                                cfg.composio_toolkit_version)
        task_sources.append(GoogleTasksSource(client, cfg.google_tasks_lists, cfg.composio_tasks_account_id))
        if cfg.google_calendar_ids:
            event_sources.append(GoogleCalendarSource(client, cfg.google_calendar_ids, cfg.timezone,
                                                      cfg.composio_calendar_account_id))
        if cfg.holiday_calendar_ids:
            event_sources.append(GoogleCalendarSource(client, cfg.holiday_calendar_ids, cfg.timezone,
                                                      cfg.composio_calendar_account_id, holiday=True))
    elif cfg.google_calendar_ids or cfg.holiday_calendar_ids:
        log.warning("GOOGLE_CALENDAR_IDS set, but COMPOSIO_API_KEY / COMPOSIO_USER_ID missing")
    if cfg.ics_urls:
        event_sources.append(IcsSource(cfg.ics_urls, cfg.timezone))
    if cfg.holiday_ics_urls:
        event_sources.append(IcsSource(cfg.holiday_ics_urls, cfg.timezone, holiday=True))
    return event_sources, task_sources


def collect(cfg: Config, start: date, end: date, today: date, event_sources=None, task_sources=None) -> PlannerData:
    if event_sources is None and task_sources is None:
        event_sources, task_sources = build_sources(cfg)
    events: list[Event] = []
    tasks: list[Task] = []
    errors: list[str] = []
    for src in event_sources or []:
        try:
            events.extend(src.fetch(start, end))
        except Exception as exc:  # one broken source must not stop the planner
            log.exception("Event source %s failed", type(src).__name__)
            errors.append(f"{type(src).__name__}: {exc}")
    for src in task_sources or []:
        try:
            tasks.extend(src.fetch(start, end))
        except Exception as exc:
            log.exception("Task source %s failed", type(src).__name__)
            errors.append(f"{type(src).__name__}: {exc}")
    return PlannerData(today=today, events=events, tasks=tasks, errors=errors)
