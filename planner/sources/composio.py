"""Minimal Composio REST client: executes a tool for a user and returns its `data` payload."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

log = logging.getLogger(__name__)


class ComposioError(RuntimeError):
    pass


class ComposioClient:
    def __init__(self, api_key: str, user_id: str, base_url: str = "https://backend.composio.dev/api/v3",
                 version: str | None = None, timeout: int = 60, session: requests.Session | None = None):
        self.api_key = api_key
        self.user_id = user_id
        self.base_url = base_url.rstrip("/")
        self.version = version
        self.timeout = timeout
        self.http = session or requests.Session()

    def execute(self, tool_slug: str, arguments: dict[str, Any], connected_account_id: str | None = None,
                retries: int = 3) -> dict[str, Any]:
        body: dict[str, Any] = {"user_id": self.user_id, "arguments": arguments}
        if connected_account_id:
            body["connected_account_id"] = connected_account_id
        if self.version:
            body["version"] = self.version

        url = f"{self.base_url}/tools/execute/{tool_slug}"
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                resp = self.http.post(url, json=body, timeout=self.timeout,
                                      headers={"x-api-key": self.api_key, "Content-Type": "application/json"})
            except requests.RequestException as exc:
                last_error = exc
            else:
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_error = ComposioError(f"{tool_slug}: HTTP {resp.status_code}")
                elif resp.status_code >= 400:
                    raise ComposioError(f"{tool_slug}: HTTP {resp.status_code}: {resp.text[:500]}")
                else:
                    return self._unwrap(tool_slug, resp.json())
            if attempt < retries:
                time.sleep(2 ** attempt)
        raise ComposioError(f"{tool_slug} failed after {retries} attempts: {last_error}")

    @staticmethod
    def _unwrap(tool_slug: str, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("successful") is False or (payload.get("error") and not payload.get("data")):
            raise ComposioError(f"{tool_slug}: {payload.get('error') or 'unsuccessful'}")
        data = payload.get("data", payload)
        # Some tools wrap the API response one level deeper.
        if isinstance(data, dict) and "response_data" in data and isinstance(data["response_data"], dict):
            data = data["response_data"]
        return data or {}

    def paginate(self, tool_slug: str, arguments: dict[str, Any], items_key: str,
                 connected_account_id: str | None = None, max_pages: int = 50) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        args = dict(arguments)
        for _ in range(max_pages):
            data = self.execute(tool_slug, args, connected_account_id)
            items.extend(data.get(items_key) or [])
            token = data.get("nextPageToken")
            if not token:
                return items
            args["pageToken"] = token
        log.warning("%s: stopped after %d pages", tool_slug, max_pages)
        return items
