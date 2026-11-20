"""Google Tasks via Composio (toolkit `googletasks`)."""
from __future__ import annotations

import logging
from datetime import date

from ..models import Task
from .composio import ComposioClient

log = logging.getLogger(__name__)


def parse_due(raw: str | None) -> date | None:
    # Google Tasks stores only the date; the API returns it as midnight UTC (2026-11-19T00:00:00.000Z).
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def to_task(item: dict, list_name: str) -> Task | None:
    if item.get("deleted") or not (item.get("title") or "").strip():
        return None
    return Task(
        title=item["title"].strip(),
        due=parse_due(item.get("due")),
        completed=item.get("status") == "completed",
        notes=item.get("notes") or "",
        list_name=list_name,
        source="google_tasks",
    )


class GoogleTasksSource:
    def __init__(self, client: ComposioClient, lists: list[str] | None = None, account_id: str | None = None):
        self.client = client
        self.wanted = [name.lower() for name in (lists or [])]
        self.account_id = account_id

    def task_lists(self) -> list[dict]:
        lists = self.client.paginate("GOOGLETASKS_LIST_TASK_LISTS", {"maxResults": 100}, "items",
                                     self.account_id)
        if not self.wanted:
            return lists
        chosen = [tl for tl in lists if tl.get("id", "").lower() in self.wanted
                  or tl.get("title", "").lower() in self.wanted]
        missing = set(self.wanted) - {tl.get("id", "").lower() for tl in chosen} \
            - {tl.get("title", "").lower() for tl in chosen}
        if missing:
            log.warning("Google Tasks lists not found: %s", ", ".join(sorted(missing)))
        return chosen

    def fetch(self, start: date, end: date) -> list[Task]:
        """Open tasks with or without due date, plus tasks completed in [start, end]."""
        tasks: list[Task] = []
        for tl in self.task_lists():
            items = self.client.paginate(
                "GOOGLETASKS_LIST_TASKS",
                {"tasklist_id": tl["id"], "maxResults": 100, "showCompleted": True, "showHidden": True},
                "tasks", self.account_id,
            )
            for item in items:
                task = to_task(item, tl.get("title", ""))
                if task is None:
                    continue
                if task.completed and task.due and not (start <= task.due <= end):
                    continue
                tasks.append(task)
        log.info("Google Tasks: %d tasks", len(tasks))
        return tasks
