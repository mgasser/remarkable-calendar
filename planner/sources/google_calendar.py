"""Google Calendar via Composio (toolkit `googlecalendar`)."""
from __future__ import annotations

import logging
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from ..models import Event
from .composio import ComposioClient

log = logging.getLogger(__name__)


def to_event(item: dict, tz: ZoneInfo, source: str, holiday: bool = False) -> Event | None:
    if item.get("status") == "cancelled":
        return None
    start, end = item.get("start") or {}, item.get("end") or {}
    title = (item.get("summary") or "").strip() or "(ohne Titel)"
    if "date" in start:
        s = date.fromisoformat(start["date"])
        e = date.fromisoformat(end.get("date", start["date"]))
        if e <= s:
            from datetime import timedelta
            e = s + timedelta(days=1)
        return Event(title, s, e, True, item.get("description") or "", source, holiday)
    if "dateTime" in start:
        s = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00")).astimezone(tz)
        e = datetime.fromisoformat((end.get("dateTime") or start["dateTime"]).replace("Z", "+00:00")).astimezone(tz)
        return Event(title, s, e, False, item.get("description") or "", source, holiday)
    return None


class GoogleCalendarSource:
    def __init__(self, client: ComposioClient, calendar_ids: list[str], tz: ZoneInfo,
                 account_id: str | None = None, holiday: bool = False):
        self.client = client
        self.calendar_ids = calendar_ids
        self.tz = tz
        self.account_id = account_id
        self.holiday = holiday

    def fetch(self, start: date, end: date) -> list[Event]:
        time_min = datetime.combine(start, time.min, self.tz).isoformat()
        time_max = datetime.combine(end, time.max.replace(microsecond=0), self.tz).isoformat()
        events: list[Event] = []
        for cal_id in self.calendar_ids:
            items = self.client.paginate(
                "GOOGLECALENDAR_EVENTS_LIST",
                {"calendarId": cal_id, "timeMin": time_min, "timeMax": time_max, "singleEvents": True,
                 "orderBy": "startTime", "maxResults": 2500, "timeZone": str(self.tz)},
                "items", self.account_id,
            )
            for item in items:
                event = to_event(item, self.tz, f"google:{cal_id}", self.holiday)
                if event:
                    events.append(event)
        log.info("Google Calendar (%s): %d events", ", ".join(self.calendar_ids), len(events))
        return events
