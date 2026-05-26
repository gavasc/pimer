from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Digits, Static

from .models import Item, ItemKind, ItemState, format_duration

# ── State helpers ─────────────────────────────────────────────────────────────

def _item_style(item: Item) -> tuple[str, str]:
    """Return (icon, rich_style) for the item state."""
    if item.kind == ItemKind.ALARM:
        if item.state == ItemState.RUNNING:
            return "⏰", "bold color(10)"
        elif item.state == ItemState.DONE:
            return "✓ ", "bold color(9)"
        return "·  ", "dim"
    if item.state == ItemState.RUNNING:
        return "▶ ", "bold color(10)"
    elif item.state == ItemState.PAUSED:
        return "⏸ ", "bold color(11)"
    elif item.state == ItemState.DONE:
        return "✓ ", "bold color(9)"
    return "·  ", "dim"



def _item_time(item: Item) -> str:
    if item.kind == ItemKind.TIMER:
        return f"{format_duration(item.remaining_secs())} / {format_duration(item.duration_secs)}"
    elif item.kind == ItemKind.ALARM:
        return "fired" if item.state == ItemState.DONE else item.target_at
    else:
        return format_duration(item.elapsed_secs)


# ── ItemListWidget ────────────────────────────────────────────────────────────

class ItemListWidget(Widget):
    can_focus = True

    class NewRequested(Message):
        pass

    class EditRequested(Message):
        def __init__(self, item: Item) -> None:
            super().__init__()
            self.item = item

    class DeleteRequested(Message):
        def __init__(self, item: Item) -> None:
            super().__init__()
            self.item = item

    class ToggleRequested(Message):
        def __init__(self, item: Item) -> None:
            super().__init__()
            self.item = item

    class ResetRequested(Message):
        def __init__(self, item: Item) -> None:
            super().__init__()
            self.item = item

    class SelectionChanged(Message):
        def __init__(self, item: Item | None, kind: ItemKind) -> None:
            super().__init__()
            self.item = item
            self.kind = kind

    def __init__(self, kind: ItemKind, **kwargs) -> None:
        super().__init__(**kwargs)
        self.kind = kind
        self._items: list[Item] = []
        self._cursor: int = 0

    def set_items(self, items: list[Item]) -> None:
        self._items = [it for it in items if it.kind == self.kind]
        if self._cursor >= len(self._items):
            self._cursor = max(len(self._items) - 1, 0)
        self.refresh()

    def _selected(self) -> Item | None:
        if self._items:
            return self._items[self._cursor]
        return None

    def render(self) -> Text:
        if not self._items:
            return Text.from_markup(
                "[dim]  No items — press [bold]n[/bold] to create one[/dim]"
            )
        t = Text()
        for i, item in enumerate(self._items):
            icon, style = _item_style(item)
            time_str = _item_time(item)
            cursor = "[bold cyan]>[/bold cyan] " if i == self._cursor else "  "
            t.append_text(Text.from_markup(cursor))
            t.append(icon + " ", style=style)
            t.append(f"{item.name:<18}  ")
            t.append(time_str, style=style)
            if i < len(self._items) - 1:
                t.append("\n")
        return t

    def on_key(self, event: events.Key) -> None:
        key = event.key

        if key in ("up", "k"):
            if self._cursor > 0:
                self._cursor -= 1
                self.refresh()
                self.post_message(self.SelectionChanged(self._selected(), self.kind))
            event.stop()

        elif key in ("down", "j"):
            if self._cursor < len(self._items) - 1:
                self._cursor += 1
                self.refresh()
                self.post_message(self.SelectionChanged(self._selected(), self.kind))
            event.stop()

        elif key in ("enter", "space"):
            if self._items:
                self.post_message(self.ToggleRequested(self._items[self._cursor]))
            event.stop()

        elif key == "n":
            self.post_message(self.NewRequested())
            event.stop()

        elif key == "e":
            if self._items:
                self.post_message(self.EditRequested(self._items[self._cursor]))
            event.stop()

        elif key == "d":
            if self._items:
                self.post_message(self.DeleteRequested(self._items[self._cursor]))
            event.stop()

        elif key == "r":
            if self._items:
                self.post_message(self.ResetRequested(self._items[self._cursor]))
            event.stop()


# ── BigTimerWidget ────────────────────────────────────────────────────────────

class BigTimerWidget(Widget):
    DEFAULT_CSS = """
    BigTimerWidget {
        align: center top;
        layout: vertical;
    }
    BigTimerWidget #big-name {
        text-align: center;
        width: 1fr;
        margin-bottom: 1;
    }
    BigTimerWidget Digits {
        text-align: center;
        width: 1fr;
    }
    BigTimerWidget #big-sub {
        text-align: center;
        width: 1fr;
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._item: Item | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="big-name")
        yield Digits("", id="big-digits")
        yield Static("", id="big-sub")

    def on_mount(self) -> None:
        self._update_display()

    def set_item(self, item: Item | None) -> None:
        self._item = item
        self._update_display()

    def _update_display(self) -> None:
        try:
            name_w   = self.query_one("#big-name", Static)
            digits_w = self.query_one("#big-digits", Digits)
            sub_w    = self.query_one("#big-sub", Static)
        except Exception:
            return  # not mounted yet

        item = self._item

        if item is None:
            name_w.update("")
            digits_w.update("")
            digits_w.set_classes("")
            sub_w.update("")
            return

        icon, rich_style = _item_style(item)

        # Name + state line
        name_text = Text()
        name_text.append(f"{icon} {item.name}", style=rich_style)
        name_text.append(f"  [{item.state.value}]", style="dim")
        name_w.update(name_text)

        # Big digits — color comes from CSS class, not inline style
        if item.kind == ItemKind.TIMER:
            time_str = format_duration(item.remaining_secs())
        elif item.kind == ItemKind.ALARM:
            time_str = item.target_at if item.state != ItemState.DONE else "done"
        else:
            time_str = format_duration(item.elapsed_secs)

        digits_w.update(time_str)
        digits_w.set_classes(item.state.value)  # "running" | "paused" | "done" | "idle"

        # Sub-line: alarm countdown only
        if item.kind == ItemKind.ALARM and item.target_datetime and item.state == ItemState.RUNNING:
            try:
                target = datetime.fromisoformat(item.target_datetime)
                secs = max((target - datetime.now()).total_seconds(), 0)
                sub_w.update(f"in {format_duration(secs)}")
            except Exception:
                sub_w.update("")
        else:
            sub_w.update("")
