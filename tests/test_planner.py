from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from planner.collect import PlannerData, collect
from planner.config import Config
from planner.generator import build, months_to_build
from planner.i18n import Lang
from planner.models import Event, Task
from planner.pages import Layout, _layout_columns
from planner.sources.composio import ComposioClient, ComposioError
from planner.sources.google_calendar import to_event
from planner.sources.google_tasks import GoogleTasksSource, to_task
from planner.sources.ics import parse_ics
from planner.__main__ import next_run

TZ = ZoneInfo("Europe/Zurich")


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code, self.text = payload, status, str(payload)

    def json(self):
        return self._payload


class FakeHttp:
    """Answers Composio calls from a dict {tool_slug: [payload, payload, ...]}."""

    def __init__(self, answers):
        self.answers = {k: list(v) for k, v in answers.items()}
        self.calls = []

    def post(self, url, json, timeout, headers):
        slug = url.rsplit("/", 1)[-1]
        self.calls.append((slug, json))
        return FakeResponse(self.answers[slug].pop(0))


def test_composio_execute_sends_user_and_key_and_unwraps():
    http = FakeHttp({"GOOGLETASKS_LIST_TASK_LISTS": [{"data": {"items": [{"id": "a"}]}, "successful": True}]})
    client = ComposioClient("key", "user-1", session=http)
    assert client.execute("GOOGLETASKS_LIST_TASK_LISTS", {"maxResults": 1}) == {"items": [{"id": "a"}]}
    assert http.calls[0][1] == {"user_id": "user-1", "arguments": {"maxResults": 1}}


def test_composio_error_raises():
    http = FakeHttp({"X": [{"data": {}, "successful": False, "error": "no connection"}]})
    with pytest.raises(ComposioError, match="no connection"):
        ComposioClient("key", "u", session=http).execute("X", {})


def test_google_tasks_paginates_and_filters_lists():
    http = FakeHttp({
        "GOOGLETASKS_LIST_TASK_LISTS": [{"data": {"items": [{"id": "L1", "title": "DO"}, {"id": "L2", "title": "INBOX"}]}}],
        "GOOGLETASKS_LIST_TASKS": [
            {"data": {"tasks": [{"title": "A", "due": "2026-11-19T00:00:00.000Z", "status": "needsAction"}],
                      "nextPageToken": "p2"}},
            {"data": {"tasks": [{"title": "B", "status": "completed", "due": "2026-11-18T00:00:00.000Z"},
                                {"title": "old", "status": "completed", "due": "2020-01-01T00:00:00.000Z"}],
                      "nextPageToken": None}},
        ],
    })
    src = GoogleTasksSource(ComposioClient("k", "u", session=http), lists=["do"])
    tasks = src.fetch(date(2026, 1, 1), date(2026, 12, 31))
    assert [t.title for t in tasks] == ["A", "B"]
    assert tasks[0].due == date(2026, 11, 19) and tasks[0].list_name == "DO"
    assert tasks[1].completed
    list_calls = [c for c in http.calls if c[0] == "GOOGLETASKS_LIST_TASKS"]
    assert list_calls[1][1]["arguments"]["pageToken"] == "p2"
    assert all(c[1]["arguments"]["tasklist_id"] == "L1" for c in list_calls)


def test_google_calendar_event_conversion():
    timed = to_event({"summary": "Call", "start": {"dateTime": "2026-11-20T08:00:00Z"},
                      "end": {"dateTime": "2026-11-20T09:30:00Z"}}, TZ, "g")
    assert timed.start.hour == 9 and timed.end.hour == 10 and not timed.all_day  # UTC+1
    allday = to_event({"summary": "Ferien", "start": {"date": "2026-11-20"}, "end": {"date": "2026-11-22"}}, TZ, "g")
    assert allday.all_day and allday.days() == [date(2026, 11, 20), date(2026, 11, 21)]
    assert to_event({"status": "cancelled", "start": {"date": "2026-11-20"}}, TZ, "g") is None


ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1
SUMMARY:Weekly @headline
DTSTART;TZID=Europe/Zurich:20261102T083000
DTEND;TZID=Europe/Zurich:20261102T090000
RRULE:FREQ=WEEKLY;COUNT=5
END:VEVENT
BEGIN:VEVENT
UID:2
SUMMARY:Night
DTSTART:20261110T230000Z
DTEND:20261111T010000Z
END:VEVENT
END:VCALENDAR
"""


def test_ics_recurrence_and_timezone():
    events = parse_ics(ICS, date(2026, 11, 1), date(2026, 11, 30), TZ)
    weekly = [e for e in events if e.title.startswith("Weekly")]
    assert len(weekly) == 5 and weekly[0].start.hour == 8 and weekly[0].headline
    night = next(e for e in events if e.title == "Night")
    # 23:00 UTC is midnight in Zurich: the event belongs to the 11th, not the 10th.
    assert night.days() == [date(2026, 11, 11)]


def test_overdue_open_tasks_move_to_today_and_duplicates_are_removed():
    today = date(2026, 11, 20)
    ev = Event("Zahnarzt", datetime(2026, 11, 20, 10, tzinfo=TZ), datetime(2026, 11, 20, 11, tzinfo=TZ))
    data = PlannerData(today, [ev], [
        Task("Rechnung zahlen", date(2026, 11, 18)),
        Task("Erledigt", date(2026, 11, 18), completed=True),
        Task("Zahnarzt", date(2026, 11, 20)),
    ])
    assert [t.title for t in data.tasks_on(today)] == ["Rechnung zahlen"]
    assert data.tasks_on(today)[0].overdue
    assert [t.title for t in data.tasks_on(date(2026, 11, 18))] == ["Erledigt"]


def test_failing_source_does_not_stop_the_run():
    class Broken:
        def fetch(self, start, end):
            raise RuntimeError("boom")

    class Ok:
        def fetch(self, start, end):
            return [Task("x", date(2026, 11, 20))]

    data = collect(Config(), date(2026, 1, 1), date(2026, 12, 31), date(2026, 11, 20), [Broken()], [Ok()])
    assert len(data.tasks) == 1 and data.errors and "boom" in data.errors[0]


def test_months_to_build_crosses_year():
    assert months_to_build(date(2026, 11, 20), 3) == [(2026, 11), (2026, 12), (2027, 1)]


def test_next_run():
    now = datetime(2026, 11, 20, 5, 0, tzinfo=TZ)
    assert next_run(now, ["04:30"]) == datetime(2026, 11, 21, 4, 30, tzinfo=TZ)
    assert next_run(now, ["04:30", "12:00"]) == datetime(2026, 11, 20, 12, 0, tzinfo=TZ)


def test_overlapping_events_get_columns():
    t = lambda h: datetime(2026, 11, 20, h, tzinfo=TZ)
    a, b, c = Event("a", t(9), t(11)), Event("b", t(10), t(12)), Event("c", t(13), t(14))
    cols = {e.title: (col, n) for e, col, n in _layout_columns([a, b, c])}
    assert cols == {"a": (0, 2), "b": (1, 2), "c": (0, 1)}


@pytest.mark.parametrize("fmt", ["remarkable", "paperpro", "move", "a4", "letter"])
def test_pdf_page_count_is_stable(tmp_path, fmt):
    """Same page count with and without data, so handwriting stays on the right page."""
    today = date(2026, 11, 20)
    layout = Layout(fmt, Lang("de"))
    empty = build(layout, PlannerData(today), [(2026, 11)], tmp_path / "a")[0]
    tasks = [Task(f"Aufgabe {i} mit einem sehr langen Titel, der abgeschnitten wird", today) for i in range(40)]
    events = [Event(f"Termin {h}", datetime(2026, 11, 20, h, tzinfo=TZ),
                    datetime(2026, 11, 20, h, tzinfo=TZ) + timedelta(hours=2)) for h in range(5, 24)]
    full = build(layout, PlannerData(today, events, tasks), [(2026, 11)], tmp_path / "b")[0]
    assert empty.name == "2026-11 November.pdf"
    pages = 4 + 1 + 6 + 30 * 2 + 10  # Nov 2026 touches 6 weeks
    from pypdf import PdfReader

    assert len(PdfReader(empty).pages) == pages == len(PdfReader(full).pages)
