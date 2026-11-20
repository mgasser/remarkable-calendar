"""ICS / iCal feeds (iCloud, Outlook, Google secret address, holiday feeds)."""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import requests

from ..models import Event

log = logging.getLogger(__name__)


def _as_local(value, tz: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def parse_ics(text: str | bytes, start: date, end: date, tz: ZoneInfo, source: str = "ics",
              holiday: bool = False) -> list[Event]:
    cal = icalendar.Calendar.from_ical(text)
    window_start = datetime.combine(start, time.min, tz)
    window_end = datetime.combine(end + timedelta(days=1), time.min, tz)
    events: list[Event] = []
    for comp in recurring_ical_events.of(cal).between(window_start, window_end):
        if str(comp.get("STATUS", "")).upper() == "CANCELLED":
            continue
        title = str(comp.get("SUMMARY", "")).strip() or "(ohne Titel)"
        desc = str(comp.get("DESCRIPTION", "") or "")
        dtstart = comp.decoded("DTSTART")
        dtend = comp.decoded("DTEND") if comp.get("DTEND") else None
        if not isinstance(dtstart, datetime):
            s = dtstart
            e = dtend if isinstance(dtend, date) and not isinstance(dtend, datetime) and dtend > s \
                else s + timedelta(days=1)
            events.append(Event(title, s, e, True, desc, source, holiday))
        else:
            s = _as_local(dtstart, tz)
            if isinstance(dtend, datetime):
                e = _as_local(dtend, tz)
            elif comp.get("DURATION"):
                e = s + comp.decoded("DURATION")
            else:
                e = s
            events.append(Event(title, s, e, False, desc, source, holiday))
    return events


class IcsSource:
    def __init__(self, urls: list[str], tz: ZoneInfo, holiday: bool = False, timeout: int = 60):
        self.urls = urls
        self.tz = tz
        self.holiday = holiday
        self.timeout = timeout

    def fetch(self, start: date, end: date) -> list[Event]:
        events: list[Event] = []
        for i, url in enumerate(self.urls, 1):
            if url.startswith("webcal://"):
                url = "https://" + url[len("webcal://"):]
            resp = requests.get(url, timeout=self.timeout)
            resp.raise_for_status()
            found = parse_ics(resp.content, start, end, self.tz, f"ics:{i}", self.holiday)
            log.info("ICS feed %d: %d events", i, len(found))
            events.extend(found)
        return events
