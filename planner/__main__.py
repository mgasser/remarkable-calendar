"""Command line: python -m planner {run|serve|auth|check|generate}"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from .collect import collect
from .config import Config, load_config
from .generator import build, months_to_build
from .i18n import Lang
from .pages import Layout

log = logging.getLogger("planner")


def _today(cfg: Config) -> date:
    return datetime.now(cfg.timezone).date()


def _write_status(cfg: Config, ok: bool, message: str, files: list[Path] | None = None) -> None:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    status = {"ok": ok, "message": message, "time": datetime.now(cfg.timezone).isoformat(timespec="seconds"),
              "files": [f.name for f in files or []]}
    cfg.status_file.write_text(json.dumps(status, indent=2))


def _ping(cfg: Config, ok: bool, message: str) -> None:
    if not cfg.healthcheck_url:
        return
    url = cfg.healthcheck_url.rstrip("/") + ("" if ok else "/fail")
    try:
        requests.post(url, data=message.encode()[:10000], timeout=10)
    except requests.RequestException as exc:
        log.warning("Healthcheck ping failed: %s", exc)


def generate(cfg: Config) -> tuple[list[Path], list[str]]:
    today = _today(cfg)
    months = months_to_build(today, cfg.months_ahead)
    # Data for the full years shown (year overview), plus the months being built.
    start = date(months[0][0], 1, 1)
    end = date(months[-1][0], 12, 31)
    data = collect(cfg, start, end, today)
    layout = Layout(cfg.page_format, Lang(cfg.language), cfg.day_start_hour, cfg.day_end_hour, cfg.notes_pages)
    files = build(layout, data, months, cfg.output_dir)
    return files, data.errors


def sync(cfg: Config, files: list[Path]) -> None:
    if cfg.sync_mode == "cloud":
        from .sync.rmcloud import CloudSync

        CloudSync(cfg.rmapi_bin, cfg.rmapi_config, cfg.remarkable_folder).upload(files)
    elif cfg.sync_mode == "ssh":
        from .sync.ssh import SshSync

        if not (cfg.remarkable_host and cfg.remarkable_password):
            raise RuntimeError("SYNC_MODE=ssh needs REMARKABLE_HOST and REMARKABLE_PASSWORD")
        SshSync(cfg.remarkable_host, cfg.remarkable_password, cfg.remarkable_folder).upload(files)
    elif cfg.sync_mode == "none":
        log.info("SYNC_MODE=none: PDFs left in %s", cfg.output_dir)
    else:
        raise RuntimeError(f"Unknown SYNC_MODE {cfg.sync_mode!r} (cloud, ssh, none)")


def run_once(cfg: Config) -> bool:
    started = time.monotonic()
    try:
        files, errors = generate(cfg)
        sync(cfg, files)
    except Exception as exc:
        log.exception("Run failed")
        _write_status(cfg, False, str(exc))
        _ping(cfg, False, str(exc))
        return False
    msg = f"{len(files)} PDFs in {time.monotonic() - started:.0f}s"
    if errors:
        msg += "; source errors: " + "; ".join(errors)
        log.warning(msg)
    else:
        log.info(msg)
    _write_status(cfg, not errors, msg, files)
    _ping(cfg, not errors, msg)
    return not errors


def next_run(now: datetime, times: list[str]) -> datetime:
    candidates = []
    for t in times:
        hh, mm = (int(x) for x in t.split(":"))
        cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand <= now:
            cand += timedelta(days=1)
        candidates.append(cand)
    return min(candidates)


def serve(cfg: Config) -> None:
    log.info("Scheduler started: daily at %s (%s), months ahead: %d, sync: %s",
             ", ".join(cfg.sync_times), cfg.timezone.key, cfg.months_ahead, cfg.sync_mode)
    if cfg.sync_mode == "cloud" and cfg.rmapi_one_time_code:
        _auth(cfg, cfg.rmapi_one_time_code, only_if_missing=True)
    if cfg.run_on_start:
        run_once(cfg)
    while True:
        now = datetime.now(cfg.timezone)
        target = next_run(now, cfg.sync_times)
        log.info("Next run: %s", target.isoformat(timespec="minutes"))
        # Sleep in chunks so clock changes (DST, suspend) do not shift the run much.
        while (remaining := (target - datetime.now(cfg.timezone)).total_seconds()) > 0:
            time.sleep(min(remaining, 300))
        run_once(cfg)


def _auth(cfg: Config, code: str | None, only_if_missing: bool = False) -> None:
    from .sync.rmcloud import CloudSync

    cs = CloudSync(cfg.rmapi_bin, cfg.rmapi_config, cfg.remarkable_folder)
    if only_if_missing and cs.authenticated:
        return
    if not code and not sys.stdin.isatty():
        raise SystemExit("No terminal. Pass the code: python -m planner auth <code> "
                         "(get it at https://my.remarkable.com/device/desktop/connect)")
    cs.authenticate(code)


def check(cfg: Config) -> int:
    """Test every configured source and the cloud login, without generating anything."""
    from .collect import build_sources

    ok = True
    today = _today(cfg)
    event_sources, task_sources = build_sources(cfg)
    if not event_sources and not task_sources:
        print("! Keine Quelle konfiguriert (COMPOSIO_*, GOOGLE_CALENDAR_IDS, ICS_URLS)")
        ok = False
    for src in event_sources + task_sources:
        name = type(src).__name__
        try:
            items = src.fetch(today, today + timedelta(days=14))
            print(f"✓ {name}: {len(items)} Einträge in den nächsten 14 Tagen")
        except Exception as exc:
            print(f"✗ {name}: {exc}")
            ok = False
    if cfg.sync_mode == "cloud":
        from .sync.rmcloud import CloudSync

        cs = CloudSync(cfg.rmapi_bin, cfg.rmapi_config, cfg.remarkable_folder)
        if not cs.authenticated:
            print(f"✗ reMarkable Cloud: nicht angemeldet ({cfg.rmapi_config} fehlt)")
            ok = False
        else:
            try:
                cs._run("ls", "/")
                print("✓ reMarkable Cloud: angemeldet")
            except Exception as exc:
                print(f"✗ reMarkable Cloud: {exc}")
                ok = False
    return 0 if ok else 1


def healthcheck(cfg: Config, max_age_hours: int = 26) -> int:
    try:
        status = json.loads(cfg.status_file.read_text())
    except (OSError, ValueError):
        return 0  # no run yet: do not flag the container before its first run
    age = datetime.now(cfg.timezone) - datetime.fromisoformat(status["time"])
    return 0 if status.get("ok") and age < timedelta(hours=max_age_hours) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="planner", description="reMarkable planner from Google Tasks/Calendar")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="Run daily at SYNC_TIMES (default for the container)")
    sub.add_parser("run", help="Generate and upload once")
    sub.add_parser("generate", help="Generate PDFs only, no upload")
    sub.add_parser("check", help="Test sources and the reMarkable login")
    auth = sub.add_parser("auth", help="Log in to the reMarkable Cloud once")
    auth.add_argument("code", nargs="?", help="One-time code from my.remarkable.com/device/desktop/connect")
    sub.add_parser("healthcheck", help="Exit 1 if the last run failed or is older than 26 h")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    cmd = args.cmd or "serve"
    if cmd == "serve":
        serve(cfg)
        return 0
    if cmd == "run":
        return 0 if run_once(cfg) else 1
    if cmd == "generate":
        files, errors = generate(cfg)
        for f in files:
            print(f)
        return 1 if errors else 0
    if cmd == "check":
        return check(cfg)
    if cmd == "auth":
        from .sync.rmcloud import RmapiError

        try:
            _auth(cfg, args.code)
        except RmapiError as exc:
            print(f"✗ Login fehlgeschlagen: {exc}\n"
                  "  Neuen Code holen: https://my.remarkable.com/device/desktop/connect", file=sys.stderr)
            return 1
        print("✓ reMarkable Cloud verbunden")
        return 0
    if cmd == "healthcheck":
        return healthcheck(cfg)
    return 2


if __name__ == "__main__":
    sys.exit(main())
