"""Background watcher: fires notifications for running timers/alarms while the UI is closed."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import notify

_STATE_PATH = Path.home() / ".local" / "share" / "pimer" / "state.json"
_PID_PATH   = Path.home() / ".local" / "share" / "pimer" / "watcher.pid"


def _read() -> tuple[datetime | None, list[dict]]:
    try:
        data = json.loads(_STATE_PATH.read_text())
        if isinstance(data, dict):
            raw = data.get("saved_at")
            return (datetime.fromisoformat(raw) if raw else None), data.get("items", [])
        return None, data
    except Exception:
        return None, []


def _write(items: list[dict]) -> None:
    _STATE_PATH.write_text(
        json.dumps({"saved_at": datetime.now().isoformat(), "items": items}, indent=2)
    )


def watch() -> None:
    _PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PID_PATH.write_text(str(os.getpid()))
    try:
        _run()
    finally:
        _PID_PATH.unlink(missing_ok=True)


def _run() -> None:
    saved_at, items = _read()
    if not saved_at:
        return

    # Compute absolute fire time for each running timer/alarm
    pending: list[tuple[datetime, str]] = []  # (fire_at, item_id)
    for item in items:
        if item.get("state") != "running":
            continue
        kind = item.get("kind")
        if kind == "timer":
            remaining = item.get("duration_secs", 0.0) - item.get("elapsed_secs", 0.0)
            pending.append((saved_at + timedelta(seconds=max(remaining, 0)), item["id"]))
        elif kind == "alarm":
            target = item.get("target_datetime")
            if target:
                pending.append((datetime.fromisoformat(target), item["id"]))

    if not pending:
        return

    while pending:
        pending.sort()
        fire_at, item_id = pending.pop(0)

        wait = (fire_at - datetime.now()).total_seconds()
        if wait > 0:
            time.sleep(wait)

        saved_at, items = _read()
        for item in items:
            if item.get("id") != item_id:
                continue
            if item.get("state") != "running":
                break
            item["state"] = "done"
            if item.get("kind") == "timer":
                item["elapsed_secs"] = item.get("duration_secs", 0.0)
            label = "alarm" if item.get("kind") == "alarm" else "timer"
            notify.fire(f"{item.get('name', '')} {label} finished")
            break
        _write(items)


if __name__ == "__main__":
    watch()
