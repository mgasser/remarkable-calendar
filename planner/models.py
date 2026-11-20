from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

_HEADLINE = re.compile(r"\s*@headline\b", re.IGNORECASE)


def clean_title(text: str) -> str:
    return _HEADLINE.sub("", text).strip()


@dataclass
class Event:
    title: str
    start: datetime | date  # aware datetime in the planner timezone, or a date for all-day events
    end: datetime | date
    all_day: bool = False
    description: str = ""
    source: str = ""
    holiday: bool = False

    @property
    def headline(self) -> bool:
        return "@headline" in f"{self.title} {self.description}".lower()

    @property
    def display(self) -> str:
        return clean_title(self.title)

    def days(self) -> list[date]:
        """Every calendar day this event touches (end is exclusive for all-day events)."""
        from datetime import timedelta

        if self.all_day:
            first, last = self.start, self.end - timedelta(days=1)
        else:
            first = self.start.date()
            # An event ending exactly at midnight does not touch the next day.
            last = (self.end - timedelta(microseconds=1)).date() if self.end > self.start else first
        last = max(first, last)
        return [first + timedelta(days=i) for i in range((last - first).days + 1)]


@dataclass
class Task:
    title: str
    due: date | None
    completed: bool = False
    notes: str = ""
    list_name: str = ""
    source: str = ""
    overdue: bool = False
    labels: list[str] = field(default_factory=list)

    @property
    def headline(self) -> bool:
        return "@headline" in f"{self.title} {self.notes}".lower()

    @property
    def display(self) -> str:
        return clean_title(self.title)
