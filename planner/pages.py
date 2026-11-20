"""Page layouts. All drawing happens in design units (a page 8.5 in wide), scaled to the real page size."""
from __future__ import annotations

import calendar
import os
from datetime import date, datetime, timedelta

from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .i18n import Lang
from .models import Event, Task

# Real page sizes in points (width, height).
PAGE_FORMATS = {
    "letter": (8.5 * inch, 11 * inch),
    "a4": (210 * mm, 297 * mm),
    "a5": (148 * mm, 210 * mm),
    "remarkable": (1404 / 226 * inch, 1872 / 226 * inch),   # reMarkable 1 / 2
    "paperpro": (1620 / 229 * inch, 2160 / 229 * inch),     # reMarkable Paper Pro
    "move": (954 / 264 * inch, 1696 / 264 * inch),          # reMarkable Paper Pro Move
}

DESIGN_W = 8.5 * inch
MARGIN = 0.5 * inch

COLOR_GRID = HexColor("#C8C8C8")
COLOR_TEXT = HexColor("#000000")
COLOR_LINK = HexColor("#1F4E79")
COLOR_EVENT = HexColor("#2C5F8D")
COLOR_EVENT_BG = HexColor("#E6EEF6")
COLOR_WEEKEND = HexColor("#F2F2F2")
COLOR_MUTED = HexColor("#707070")

FONT_HEADER = "Courier-Bold"
FONT_BODY = "Courier"

_FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
]


def register_fonts() -> None:
    """Use DejaVu Sans Mono when installed (full Unicode); fall back to the built-in Courier."""
    global FONT_HEADER, FONT_BODY
    for regular, bold in _FONT_CANDIDATES:
        if os.path.exists(regular) and os.path.exists(bold):
            if "PlannerMono" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("PlannerMono", regular))
                pdfmetrics.registerFont(TTFont("PlannerMono-Bold", bold))
            FONT_BODY, FONT_HEADER = "PlannerMono", "PlannerMono-Bold"
            return


class Layout:
    def __init__(self, page_format: str = "remarkable", lang: Lang | None = None,
                 day_start: int = 6, day_end: int = 22, notes_pages: int = 10):
        if page_format not in PAGE_FORMATS:
            raise ValueError(f"Unknown PAGE_FORMAT {page_format!r}; use one of {', '.join(PAGE_FORMATS)}")
        self.page_size = PAGE_FORMATS[page_format]
        self.scale = self.page_size[0] / DESIGN_W
        self.W = DESIGN_W
        self.H = self.page_size[1] / self.scale
        self.lang = lang or Lang("de")
        self.day_start = max(0, min(day_start, 23))
        self.day_end = max(self.day_start + 1, min(day_end, 24))
        self.notes_pages = max(0, notes_pages)


def fit(c, text: str, font: str, size: float, width: float) -> str:
    if c.stringWidth(text, font, size) <= width:
        return text
    while text and c.stringWidth(text + "…", font, size) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def day_key(d: date, kind: str = "schedule") -> str:
    return f"day_{d:%Y_%m_%d}_{kind}"


def week_key(week_start: date) -> str:
    return f"week_{week_start:%Y_%m_%d}"


def week_start_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


class PlannerPage:
    def __init__(self, layout: Layout, bookmark: str | None):
        self.L = layout
        self.bookmark = bookmark
        self.links: list[tuple[tuple[float, float, float, float], str]] = []

    def link(self, x1, y1, x2, y2, dest: str) -> None:
        self.links.append(((x1, y1, x2, y2), dest))

    def render(self, c) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    # Shared header with links month / year / week / notes.
    def _day_header(self, c, d: date, y: float, link_kind: str) -> None:
        L, lang = self.L, self.L.lang
        size = 14
        x = MARGIN
        parts = [
            (f"{lang.weekday(d)}, {d.day}. " if lang.code == "de" else f"{lang.weekday(d)}, ", None),
            (lang.month(d.month), f"month_{d:%Y_%m}"),
            (" " if lang.code == "de" else f" {d.day}, ", None),
            (str(d.year), f"year_{d.year}_page{(d.month - 1) // 3 + 1}"),
            ("  ", None),
            (lang["week"].format(num=d.isocalendar()[1]), week_key(week_start_of(d))),
        ]
        for text, dest in parts:
            c.setFont(FONT_HEADER, size)
            c.setFillColor(COLOR_LINK if dest else COLOR_TEXT)
            c.drawString(x, y, text)
            w = c.stringWidth(text, FONT_HEADER, size)
            if dest:
                self.link(x, y - 4, x + w, y + size, dest)
            x += w
        # Switch between the two pages of a day, and jump to notes.
        other_kind, other_label = ("tasks", "→ " + lang["tasks"]) if link_kind == "schedule" \
            else ("schedule", "→ " + lang["time"])
        c.setFont(FONT_BODY, 10)
        c.setFillColor(COLOR_LINK)
        right = L.W - MARGIN
        for label, dest in ((f"→ {lang['notes']}", "notes"), (other_label, day_key(d, other_kind))):
            w = c.stringWidth(label, FONT_BODY, 10)
            c.drawString(right - w, y, label)
            self.link(right - w, y - 4, right, y + 12, dest)
            right -= w + 12
        c.setFillColor(COLOR_TEXT)


class YearlyOverviewPage(PlannerPage):
    """Three months side by side, one row per weekday-aligned day."""

    def __init__(self, layout, year: int, page_num: int, current_month: int, headlines: dict[date, list[str]]):
        super().__init__(layout, f"year_{year}_page{page_num}")
        self.year, self.page_num, self.current_month = year, page_num, current_month
        self.headlines = headlines

    def render(self, c):
        L, lang = self.L, self.L.lang
        c.setFont(FONT_HEADER, 16)
        c.drawString(MARGIN, L.H - 0.55 * inch, lang["overview"].format(year=self.year, page=self.page_num))
        # Page tabs 1-4
        c.setFont(FONT_BODY, 11)
        for p in range(1, 5):
            x = L.W - MARGIN - (5 - p) * 0.35 * inch
            c.setFillColor(COLOR_TEXT if p == self.page_num else COLOR_LINK)
            c.drawString(x, L.H - 0.55 * inch, str(p))
            if p != self.page_num:
                self.link(x - 3, L.H - 0.6 * inch, x + 12, L.H - 0.4 * inch, f"year_{self.year}_page{p}")
        c.setFillColor(COLOR_TEXT)

        dow_w = 0.2 * inch
        grid_x = MARGIN + dow_w
        grid_y = MARGIN
        grid_w = L.W - 2 * MARGIN - dow_w
        grid_h = L.H - 1.1 * inch - grid_y
        rows = 37
        row_h = grid_h / rows
        month_w = grid_w / 3
        start_month = (self.page_num - 1) * 3 + 1

        c.setStrokeColor(COLOR_GRID)
        c.setLineWidth(0.5)
        letters = lang["days_letter"]
        c.setFont(FONT_BODY, 8)
        for i in range(rows):
            c.drawString(MARGIN + 2, grid_y + grid_h - (i + 0.7) * row_h, letters[i % 7])
        for i in range(rows + 1):
            yy = grid_y + grid_h - i * row_h
            c.line(MARGIN, yy, grid_x + grid_w, yy)
        c.line(MARGIN, grid_y, MARGIN, grid_y + grid_h)

        for i in range(3):
            month = start_month + i
            mx = grid_x + i * month_w
            c.setStrokeColor(COLOR_GRID)
            c.line(mx, grid_y, mx, grid_y + grid_h)
            c.setFont(FONT_HEADER, 11)
            label = lang.month(month)
            if month == self.current_month:
                c.setFillColor(COLOR_LINK)
                self.link(mx, grid_y + grid_h + 2, mx + month_w, grid_y + grid_h + 16, f"month_{self.year}_{month:02d}")
            c.drawString(mx + 4, grid_y + grid_h + 5, label)
            c.setFillColor(COLOR_TEXT)
            self._month_column(c, mx, grid_y + grid_h, month_w, row_h, month)
        c.line(grid_x + grid_w, grid_y, grid_x + grid_w, grid_y + grid_h)

    def _month_column(self, c, x, top, width, row_h, month):
        first = date(self.year, month, 1)
        date_w = 0.25 * inch
        c.line(x + date_w, top - 37 * row_h, x + date_w, top)
        for day in range(1, calendar.monthrange(self.year, month)[1] + 1):
            d = date(self.year, month, day)
            row = first.weekday() + day - 1
            y_top = top - row * row_h
            text_y = y_top - row_h * 0.72
            if d.weekday() >= 5:
                c.setFillColor(COLOR_WEEKEND)
                c.rect(x + 0.5, y_top - row_h + 0.5, width - 1, row_h - 1, fill=1, stroke=0)
            c.setFont(FONT_BODY, 8)
            c.setFillColor(COLOR_LINK if month == self.current_month else COLOR_TEXT)
            c.drawRightString(x + date_w - 2, text_y, str(day))
            if month == self.current_month:
                self.link(x, y_top - row_h, x + date_w, y_top, day_key(d))
            items = self.headlines.get(d)
            if items:
                c.setFillColor(COLOR_EVENT)
                c.setFont(FONT_BODY, 7)
                c.drawString(x + date_w + 2, text_y, fit(c, " · ".join(items), FONT_BODY, 7, width - date_w - 22))
            if d.weekday() == 0:
                c.setFillColor(COLOR_MUTED)
                c.setFont(FONT_BODY, 6)
                c.drawRightString(x + width - 2, text_y, str(d.isocalendar()[1]))
        c.setFillColor(COLOR_TEXT)


class MonthlyOverviewPage(PlannerPage):
    def __init__(self, layout, year: int, month: int, events_on, headlines: dict[date, list[str]]):
        super().__init__(layout, f"month_{year}_{month:02d}")
        self.year, self.month = year, month
        self.events_on = events_on
        self.headlines = headlines

    def render(self, c):
        L, lang = self.L, self.L.lang
        c.setFont(FONT_HEADER, 18)
        c.drawString(MARGIN, L.H - 0.6 * inch, f"{lang.month(self.month)} ")
        w = c.stringWidth(f"{lang.month(self.month)} ", FONT_HEADER, 18)
        c.setFillColor(COLOR_LINK)
        c.drawString(MARGIN + w, L.H - 0.6 * inch, str(self.year))
        self.link(MARGIN + w, L.H - 0.65 * inch, MARGIN + w + c.stringWidth(str(self.year), FONT_HEADER, 18),
                  L.H - 0.4 * inch, f"year_{self.year}_page{(self.month - 1) // 3 + 1}")
        c.setFillColor(COLOR_TEXT)

        wk_w = 0.35 * inch
        grid_x, grid_y = MARGIN + wk_w, MARGIN
        grid_w = L.W - 2 * MARGIN - wk_w
        grid_h = L.H - 1.25 * inch - grid_y
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(self.year, self.month)
        col_w, row_h = grid_w / 7, grid_h / len(weeks)

        c.setFont(FONT_HEADER, 11)
        for i, name in enumerate(lang["days_short"]):
            c.drawString(grid_x + i * col_w + 4, grid_y + grid_h + 6, name)

        for r, week in enumerate(weeks):
            y_top = grid_y + grid_h - r * row_h
            c.setFont(FONT_BODY, 9)
            c.setFillColor(COLOR_LINK)
            c.drawString(MARGIN, y_top - 14, str(week[0].isocalendar()[1]))
            self.link(MARGIN, y_top - row_h, grid_x, y_top, week_key(week[0]))
            for col, d in enumerate(week):
                cx = grid_x + col * col_w
                if d.weekday() >= 5:
                    c.setFillColor(COLOR_WEEKEND)
                    c.rect(cx, y_top - row_h, col_w, row_h, fill=1, stroke=0)
                if d.month != self.month:
                    continue
                c.setFillColor(COLOR_LINK)
                c.setFont(FONT_HEADER, 12)
                c.drawString(cx + 4, y_top - 15, str(d.day))
                self.link(cx, y_top - row_h, cx + col_w, y_top, day_key(d))
                lines = list(self.headlines.get(d, []))
                for ev in self.events_on(d):
                    if ev.display in lines:
                        continue
                    lines.append(ev.display if ev.all_day else f"{ev.start:%H:%M} {ev.display}")
                c.setFont(FONT_BODY, 6.5)
                c.setFillColor(COLOR_EVENT)
                max_lines = max(0, int((row_h - 22) // 8))
                for i, text in enumerate(lines[:max_lines]):
                    if i == max_lines - 1 and len(lines) > max_lines:
                        text = lang["more"].format(n=len(lines) - i)
                    c.drawString(cx + 3, y_top - 26 - i * 8, fit(c, text, FONT_BODY, 6.5, col_w - 6))
        c.setStrokeColor(COLOR_GRID)
        c.setLineWidth(0.5)
        for r in range(len(weeks) + 1):
            yy = grid_y + grid_h - r * row_h
            c.line(MARGIN, yy, grid_x + grid_w, yy)
        for col in range(8):
            c.line(grid_x + col * col_w, grid_y, grid_x + col * col_w, grid_y + grid_h)
        c.setFillColor(COLOR_TEXT)


def _layout_columns(events: list[Event]) -> list[tuple[Event, int, int]]:
    """Assign overlapping timed events to side-by-side columns: (event, column, columns_in_cluster)."""
    result: list[tuple[Event, int, int]] = []
    cluster: list[tuple[Event, int]] = []
    cluster_end = None
    col_ends: list[datetime] = []

    def flush():
        n = max((col for _, col in cluster), default=-1) + 1
        result.extend((ev, col, n) for ev, col in cluster)

    for ev in sorted(events, key=lambda e: (e.start, e.end)):
        if cluster_end is not None and ev.start >= cluster_end:
            flush()
            cluster, col_ends = [], []
            cluster_end = None
        for i, end in enumerate(col_ends):
            if ev.start >= end:
                col_ends[i] = ev.end
                cluster.append((ev, i))
                break
        else:
            col_ends.append(ev.end)
            cluster.append((ev, len(col_ends) - 1))
        cluster_end = ev.end if cluster_end is None else max(cluster_end, ev.end)
    flush()
    return result


def _clip(ev: Event, d: date, start_h: int, end_h: int, tz) -> tuple[float, float] | None:
    """Return the event's span on day d in fractional hours, clipped to the visible range."""
    day_start = datetime.combine(d, datetime.min.time(), tz)
    s = max((ev.start - day_start).total_seconds() / 3600, start_h)
    e = min((ev.end - day_start).total_seconds() / 3600, end_h)
    if e <= s:
        if start_h <= s < end_h:  # zero-length event: show a thin block
            return s, min(s + 0.25, end_h)
        return None
    return s, e


class WeeklyPage(PlannerPage):
    def __init__(self, layout, week_start: date, events_on):
        super().__init__(layout, week_key(week_start))
        self.week_start = week_start
        self.events_on = events_on

    def render(self, c):
        L, lang = self.L, self.L.lang
        ws, we = self.week_start, self.week_start + timedelta(days=6)
        c.setFont(FONT_HEADER, 16)
        c.drawString(MARGIN, L.H - 0.6 * inch,
                     f"{lang['week'].format(num=ws.isocalendar()[1])}  {lang.short_date(ws)} – {lang.long_date(we)}")
        c.setFont(FONT_BODY, 10)
        c.setFillColor(COLOR_LINK)
        label = f"→ {lang['notes']}"
        lw = c.stringWidth(label, FONT_BODY, 10)
        c.drawString(L.W - MARGIN - lw, L.H - 0.6 * inch, label)
        self.link(L.W - MARGIN - lw, L.H - 0.65 * inch, L.W - MARGIN, L.H - 0.45 * inch, "notes")
        c.setFillColor(COLOR_TEXT)

        time_w = 0.45 * inch
        x0, y0 = MARGIN, MARGIN
        width = L.W - 2 * MARGIN
        top = L.H - 1.2 * inch
        allday_h = 0.45 * inch
        grid_top = top - allday_h
        hours = L.day_end - L.day_start
        hour_h = (grid_top - y0) / hours
        col_w = (width - time_w) / 7

        for i in range(7):
            d = ws + timedelta(days=i)
            cx = x0 + time_w + i * col_w
            if d.weekday() >= 5:
                c.setFillColor(COLOR_WEEKEND)
                c.rect(cx, y0, col_w, top - y0, fill=1, stroke=0)
            c.setFillColor(COLOR_LINK)
            c.setFont(FONT_HEADER, 10)
            c.drawString(cx + 3, top + 6, f"{lang['days_short'][i]} {d.day}")
            self.link(cx, top, cx + col_w, top + 18, day_key(d))
            # All-day events
            c.setFont(FONT_BODY, 6.5)
            c.setFillColor(COLOR_EVENT)
            for j, ev in enumerate([e for e in self.events_on(d) if e.all_day][:3]):
                c.drawString(cx + 2, top - 9 - j * 8, fit(c, ev.display, FONT_BODY, 6.5, col_w - 4))

        c.setStrokeColor(COLOR_GRID)
        c.setLineWidth(0.5)
        c.setFillColor(COLOR_TEXT)
        c.setFont(FONT_BODY, 8)
        for h in range(hours + 1):
            yy = grid_top - h * hour_h
            c.line(x0, yy, x0 + width, yy)
            if h < hours:
                c.drawString(x0 + 2, yy - 10, f"{L.day_start + h:02d}:00")
        c.setDash(1, 2)
        for h in range(hours):
            yy = grid_top - (h + 0.5) * hour_h
            c.line(x0 + time_w, yy, x0 + width, yy)
        c.setDash()
        c.line(x0, top, x0 + width, top)
        for i in range(8):
            xx = x0 + time_w + i * col_w
            c.line(xx, y0, xx, top + 18)
        c.line(x0, y0, x0, top)

        tz = None
        for i in range(7):
            d = ws + timedelta(days=i)
            timed = [e for e in self.events_on(d) if not e.all_day]
            for ev, col, n in _layout_columns(timed):
                tz = ev.start.tzinfo
                span = _clip(ev, d, L.day_start, L.day_end, tz)
                if not span:
                    continue
                s, e = span
                sub_w = (col_w - 2) / n
                ex = x0 + time_w + i * col_w + 1 + col * sub_w
                ey_top = grid_top - (s - L.day_start) * hour_h
                eh = (e - s) * hour_h
                c.setFillColor(COLOR_EVENT_BG)
                c.rect(ex, ey_top - eh, sub_w - 1, eh, fill=1, stroke=0)
                c.setFillColor(COLOR_EVENT)
                c.setFont(FONT_BODY, 6)
                c.drawString(ex + 1.5, ey_top - 7, fit(c, ev.display, FONT_BODY, 6, sub_w - 3))
        c.setFillColor(COLOR_TEXT)


class DailySchedulePage(PlannerPage):
    def __init__(self, layout, d: date, events: list[Event]):
        super().__init__(layout, day_key(d))
        self.d = d
        self.events = events

    def render(self, c):
        L, lang = self.L, self.L.lang
        self._day_header(c, self.d, L.H - 0.6 * inch, "schedule")
        x0, y0 = MARGIN, MARGIN
        width = L.W - 2 * MARGIN
        top = L.H - 0.95 * inch

        all_day = [e for e in self.events if e.all_day]
        if all_day:
            c.setFont(FONT_BODY, 10)
            c.setFillColor(COLOR_EVENT)
            text = f"{lang['all_day']}: " + " · ".join(e.display for e in all_day)
            c.drawString(x0, top - 12, fit(c, text, FONT_BODY, 10, width))
            top -= 22
        c.setFillColor(COLOR_TEXT)

        hours = L.day_end - L.day_start
        hour_h = (top - y0) / hours
        time_w = 0.6 * inch
        c.setStrokeColor(COLOR_GRID)
        c.setLineWidth(0.5)
        c.setFont(FONT_BODY, 10)
        for h in range(hours + 1):
            yy = top - h * hour_h
            c.line(x0, yy, x0 + width, yy)
            if h < hours:
                c.drawString(x0 + 3, yy - 12, f"{L.day_start + h:02d}:00")
        c.setDash(1, 3)
        for h in range(hours):
            yy = top - (h + 0.5) * hour_h
            c.line(x0 + time_w, yy, x0 + width, yy)
        c.setDash()
        c.line(x0 + time_w, y0, x0 + time_w, top)

        timed = [e for e in self.events if not e.all_day]
        avail = width - time_w - 4
        for ev, col, n in _layout_columns(timed):
            span = _clip(ev, self.d, L.day_start, L.day_end, ev.start.tzinfo)
            if not span:
                continue
            s, e = span
            sub_w = avail / n
            ex = x0 + time_w + 2 + col * sub_w
            ey_top = top - (s - L.day_start) * hour_h
            eh = (e - s) * hour_h
            c.setFillColor(COLOR_EVENT_BG)
            c.rect(ex, ey_top - eh, sub_w - 2, eh, fill=1, stroke=0)
            c.setFillColor(COLOR_EVENT)
            c.setFont(FONT_BODY, 9)
            label = f"{ev.start:%H:%M}–{ev.end:%H:%M} {ev.display}"
            c.drawString(ex + 3, ey_top - 10, fit(c, label, FONT_BODY, 9, sub_w - 6))
        c.setFillColor(COLOR_TEXT)


class DailyTasksPage(PlannerPage):
    def __init__(self, layout, d: date, tasks: list[Task], headlines: list[str]):
        super().__init__(layout, day_key(d, "tasks"))
        self.d = d
        self.tasks = tasks
        self.headlines = headlines

    def render(self, c):
        L, lang = self.L, self.L.lang
        self._day_header(c, self.d, L.H - 0.6 * inch, "tasks")
        x, width = MARGIN, L.W - 2 * MARGIN
        y = L.H - 1.0 * inch

        if self.headlines:
            c.setFont(FONT_HEADER, 11)
            c.setFillColor(COLOR_EVENT)
            c.drawString(x, y - 12, fit(c, f"{lang['headlines']}: " + " · ".join(self.headlines),
                                        FONT_HEADER, 11, width))
            c.setFillColor(COLOR_TEXT)
            y -= 26

        avail = y - MARGIN
        # Fixed split, so the page layout never moves between syncs (handwriting stays in place).
        prio_h, tasks_h = avail * 0.2, avail * 0.5
        summary_h = avail - prio_h - tasks_h - 2 * 0.15 * inch
        y = self._section(c, x, y, width, prio_h, lang["priorities"], 3)
        y = self._tasks(c, x, y - 0.15 * inch, width, tasks_h)
        self._section(c, x, y - 0.15 * inch, width, summary_h, lang["summary"], 0)

    def _section(self, c, x, y_top, width, height, title, lines):
        c.setFont(FONT_HEADER, 11)
        c.drawString(x + 4, y_top - 14, title)
        c.setStrokeColor(COLOR_GRID)
        c.setLineWidth(0.5)
        c.rect(x, y_top - height, width, height)
        if lines:
            lh = (height - 20) / lines
            for i in range(1, lines):
                c.line(x, y_top - 20 - i * lh, x + width, y_top - 20 - i * lh)
        return y_top - height

    def _tasks(self, c, x, y_top, width, height):
        lang = self.L.lang
        self._section(c, x, y_top, width, height, lang["tasks"], 0)
        row_h = 0.3 * inch
        rows = int((height - 22) // row_h)
        c.setStrokeColor(COLOR_GRID)
        for i in range(1, rows + 1):
            c.line(x, y_top - 20 - i * row_h, x + width, y_top - 20 - i * row_h)
        tasks = self.tasks
        if len(tasks) > rows:
            tasks = tasks[: rows - 1]
        box = 8
        for i, task in enumerate(tasks):
            ty = y_top - 20 - (i + 1) * row_h + 7
            c.setStrokeColor(COLOR_TEXT)
            c.rect(x + 6, ty, box, box)
            if task.completed:
                c.line(x + 7, ty + 1, x + 5 + box, ty + box - 1)
                c.line(x + 7, ty + box - 1, x + 5 + box, ty + 1)
            text = task.display
            if task.overdue and task.due:
                text += f"  ({lang['overdue']} {lang.short_date(task.due)})"
            c.setFont(FONT_BODY, 10)
            c.setFillColor(COLOR_MUTED if task.completed else COLOR_TEXT)
            c.drawString(x + 20, ty, fit(c, text, FONT_BODY, 10, width - 26))
        if len(self.tasks) > len(tasks):
            c.setFont(FONT_BODY, 9)
            c.setFillColor(COLOR_MUTED)
            c.drawString(x + 20, y_top - 20 - rows * row_h + 7,
                         lang["more"].format(n=len(self.tasks) - len(tasks)))
        c.setFillColor(COLOR_TEXT)
        c.setStrokeColor(COLOR_GRID)
        return y_top - height


class NotesPage(PlannerPage):
    def __init__(self, layout, page_num: int):
        super().__init__(layout, "notes" if page_num == 1 else None)
        self.page_num = page_num

    def render(self, c):
        L = self.L
        c.setFont(FONT_HEADER, 12)
        c.drawString(MARGIN, L.H - 0.55 * inch,
                     L.lang["notes_title"].format(page=self.page_num, total=L.notes_pages))
        c.setFillColor(COLOR_GRID)
        step = 0.2 * inch
        x = MARGIN
        while x <= L.W - MARGIN:
            y = MARGIN
            while y <= L.H - 0.8 * inch:
                c.circle(x, y, 0.6, fill=1, stroke=0)
                y += step
            x += step
        c.setFillColor(COLOR_TEXT)
