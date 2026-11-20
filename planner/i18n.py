"""Tiny translation table, so the planner does not depend on system locales in the container."""
from __future__ import annotations

from datetime import date

TEXT = {
    "en": {
        "months": ["January", "February", "March", "April", "May", "June", "July",
                   "August", "September", "October", "November", "December"],
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "days_short": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "days_letter": ["M", "T", "W", "T", "F", "S", "S"],
        "overview": "{year} Overview ({page}/4)",
        "week": "Week {num}",
        "time": "Time",
        "notes": "Notes",
        "notes_title": "Notes ({page}/{total})",
        "priorities": "Top 3 Priorities",
        "tasks": "Tasks",
        "summary": "Daily Summary",
        "headlines": "* Headlines",
        "all_day": "All day",
        "overdue": "overdue",
        "more": "+{n} more",
    },
    "de": {
        "months": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                   "August", "September", "Oktober", "November", "Dezember"],
        "days": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
        "days_short": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
        "days_letter": ["M", "D", "M", "D", "F", "S", "S"],
        "overview": "Jahresübersicht {year} ({page}/4)",
        "week": "KW {num}",
        "time": "Zeit",
        "notes": "Notizen",
        "notes_title": "Notizen ({page}/{total})",
        "priorities": "Top 3 Prioritäten",
        "tasks": "Aufgaben",
        "summary": "Tagesrückblick",
        "headlines": "* Highlights",
        "all_day": "Ganztägig",
        "overdue": "überfällig",
        "more": "+{n} weitere",
    },
}


class Lang:
    def __init__(self, code: str):
        self.code = code if code in TEXT else "en"
        self.t = TEXT[self.code]

    def __getitem__(self, key: str):
        return self.t[key]

    def month(self, m: int) -> str:
        return self.t["months"][m - 1]

    def weekday(self, d: date) -> str:
        return self.t["days"][d.weekday()]

    def short_date(self, d: date) -> str:
        if self.code == "de":
            return f"{d.day}. {self.month(d.month)[:3]}"
        return f"{self.month(d.month)[:3]} {d.day}"

    def long_date(self, d: date) -> str:
        if self.code == "de":
            return f"{d.day}. {self.month(d.month)} {d.year}"
        return f"{self.month(d.month)} {d.day}, {d.year}"
