"""Builds one PDF per month: year overview, month, weeks, two pages per day, notes."""
from __future__ import annotations

import calendar
import logging
import os
from datetime import date, timedelta
from pathlib import Path

from reportlab.pdfgen import canvas

from . import pages as P
from .collect import PlannerData
from .i18n import Lang

log = logging.getLogger(__name__)


def month_filename(year: int, month: int, lang: Lang) -> str:
    # The document name on the tablet. It must stay stable, so updates replace the same document.
    return f"{year}-{month:02d} {lang.month(month)}"


def months_to_build(today: date, months_ahead: int) -> list[tuple[int, int]]:
    result, y, m = [], today.year, today.month
    for _ in range(months_ahead):
        result.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return result


def build_month(layout: P.Layout, data: PlannerData, year: int, month: int, out_dir: Path) -> Path:
    lang = layout.lang
    headlines = data.headline_map(year)
    pages: list[P.PlannerPage] = [
        P.YearlyOverviewPage(layout, year, i, month, headlines) for i in range(1, 5)
    ]
    pages.append(P.MonthlyOverviewPage(layout, year, month, data.events_on, headlines))

    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    ws = P.week_start_of(first)
    while ws <= last:
        pages.append(P.WeeklyPage(layout, ws, data.events_on))
        ws += timedelta(days=7)

    d = first
    while d <= last:
        pages.append(P.DailySchedulePage(layout, d, data.events_on(d)))
        pages.append(P.DailyTasksPage(layout, d, data.tasks_on(d), data.headlines_on(d)))
        d += timedelta(days=1)
    pages.extend(P.NotesPage(layout, i) for i in range(1, layout.notes_pages + 1))

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{month_filename(year, month, lang)}.pdf"
    tmp = path.with_suffix(".pdf.tmp")
    c = canvas.Canvas(str(tmp), pagesize=layout.page_size, pageCompression=1)
    c.setTitle(f"{lang.month(month)} {year}")
    c.setAuthor("remarkable-calendar")

    bookmarks = {p.bookmark for p in pages if p.bookmark}
    for page in pages:
        c.saveState()
        c.scale(layout.scale, layout.scale)
        if page.bookmark:
            c.bookmarkPage(page.bookmark)
        page.render(c)
        for rect, dest in page.links:
            if dest in bookmarks:  # links to other months' days would dangle
                c.linkRect("", dest, rect, relative=1, thickness=0)
        c.restoreState()
        c.showPage()
    c.save()
    os.replace(tmp, path)
    log.info("Generated %s (%d pages)", path.name, len(pages))
    return path


def build(layout: P.Layout, data: PlannerData, months: list[tuple[int, int]], out_dir: Path) -> list[Path]:
    P.register_fonts()
    return [build_month(layout, data, y, m, out_dir) for y, m in months]
