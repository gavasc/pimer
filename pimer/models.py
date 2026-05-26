from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path


class ItemKind(str, Enum):
    TIMER     = "timer"
    ALARM     = "alarm"
    STOPWATCH = "stopwatch"


class ItemState(str, Enum):
    IDLE    = "idle"
    RUNNING = "running"
    PAUSED  = "paused"
    DONE    = "done"


@dataclass
class Item:
    id:              str       = field(default_factory=lambda: str(uuid.uuid4()))
    kind:            ItemKind  = ItemKind.TIMER
    name:            str       = ""
    state:           ItemState = ItemState.IDLE
    duration_secs:   float     = 0.0
    elapsed_secs:    float     = 0.0
    target_at:       str       = ""   # alarm HH:MM
    target_datetime: str       = ""   # alarm ISO next-fire datetime
    created_at:      str       = field(default_factory=lambda: datetime.now().isoformat())

    def remaining_secs(self) -> float:
        return max(self.duration_secs - self.elapsed_secs, 0.0)

    def alarm_target_dt(self) -> datetime | None:
        if not self.target_datetime:
            return None
        return datetime.fromisoformat(self.target_datetime)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"]  = self.kind.value
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Item:
        d = dict(d)
        d["kind"]  = ItemKind(d["kind"])
        d["state"] = ItemState(d["state"])
        return cls(**d)


def parse_alarm_time(hhmm: str) -> datetime:
    t = datetime.strptime(hhmm.strip(), "%H:%M")
    now = datetime.now()
    target = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def rearm_alarm(item: Item) -> None:
    item.target_datetime = parse_alarm_time(item.target_at).isoformat()
    item.state = ItemState.RUNNING


def format_duration(total_secs: float) -> str:
    total = int(max(total_secs, 0))
    h, rem = divmod(total, 3600)
    m, s   = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def parse_duration(raw: str) -> float:
    raw = raw.strip().lower()
    if not raw:
        raise ValueError("duration cannot be empty")
    if raw.isdigit():
        v = float(raw)
        if v <= 0:
            raise ValueError("duration must be > 0")
        return v
    m = re.fullmatch(r'(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?', raw)
    if not m or not any(m.groups()):
        raise ValueError(f"invalid duration {raw!r} — use e.g. 5m or 1h30m")
    h  = int(m.group(1) or 0)
    mn = int(m.group(2) or 0)
    s  = int(m.group(3) or 0)
    total = h * 3600 + mn * 60 + s
    if total <= 0:
        raise ValueError("duration must be > 0")
    return float(total)


def secs_to_human(secs: float) -> str:
    total = int(secs)
    h, r  = divmod(total, 3600)
    m, s  = divmod(r, 60)
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return "".join(parts)


_STATE_PATH = Path.home() / ".local" / "share" / "pimer" / "state.json"


class Store:
    def __init__(self, path: Path = _STATE_PATH) -> None:
        self.path  = path
        self.items: list[Item] = []

    def load(self) -> None:
        if not self.path.exists():
            self.items = []
            return
        try:
            data = json.loads(self.path.read_text())
            if isinstance(data, list):
                self.items = [Item.from_dict(d) for d in data]
                saved_at = None
            else:
                self.items = [Item.from_dict(d) for d in data.get("items", [])]
                raw = data.get("saved_at")
                saved_at = datetime.fromisoformat(raw) if raw else None
        except Exception:
            self.items = []
            return

        if saved_at is None:
            for item in self.items:
                if item.state == ItemState.RUNNING and item.kind != ItemKind.ALARM:
                    item.state = ItemState.PAUSED
            return

        delta = (datetime.now() - saved_at).total_seconds()
        for item in self.items:
            if item.state != ItemState.RUNNING or item.kind == ItemKind.ALARM:
                continue
            if item.kind == ItemKind.TIMER:
                item.elapsed_secs = min(item.elapsed_secs + delta, item.duration_secs)
                if item.elapsed_secs >= item.duration_secs:
                    item.state = ItemState.DONE
            elif item.kind == ItemKind.STOPWATCH:
                item.elapsed_secs += delta

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {"saved_at": datetime.now().isoformat(), "items": [it.to_dict() for it in self.items]},
                indent=2,
            )
        )

    def get_by_kind(self, kind: ItemKind) -> list[Item]:
        return [it for it in self.items if it.kind == kind]

    def get_by_id(self, item_id: str) -> Item | None:
        return next((it for it in self.items if it.id == item_id), None)

    def add(self, item: Item) -> None:
        self.items.append(item)
        self.save()

    def update(self, item: Item) -> None:
        for i, it in enumerate(self.items):
            if it.id == item.id:
                self.items[i] = item
                break
        self.save()

    def delete(self, item_id: str) -> None:
        self.items = [it for it in self.items if it.id != item_id]
        self.save()

    def tick(self) -> list[Item]:
        now = datetime.now()
        fired: list[Item] = []
        changed = False

        for item in self.items:
            if item.state != ItemState.RUNNING:
                continue

            if item.kind == ItemKind.TIMER:
                item.elapsed_secs += 0.5
                if item.elapsed_secs >= item.duration_secs:
                    item.elapsed_secs = item.duration_secs
                    item.state = ItemState.DONE
                    fired.append(item)
                changed = True

            elif item.kind == ItemKind.ALARM:
                target = item.alarm_target_dt()
                if target and now >= target:
                    item.state = ItemState.DONE
                    fired.append(item)
                    changed = True

            elif item.kind == ItemKind.STOPWATCH:
                item.elapsed_secs += 0.5
                changed = True

        if changed:
            self.save()
        return fired
