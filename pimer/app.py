from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.color import Color
from textual.containers import Vertical
from textual.widgets import Footer, TabPane, TabbedContent

from . import notify
from .models import Item, ItemKind, ItemState, Store, rearm_alarm
from .screens import FormScreen
from .widgets import BigTimerWidget, ItemListWidget

_KINDS      = [ItemKind.TIMER, ItemKind.ALARM, ItemKind.STOPWATCH]
_PID_PATH   = Path.home() / ".local" / "share" / "pimer" / "watcher.pid"


def _kill_watcher() -> None:
    if not _PID_PATH.exists():
        return
    try:
        pid = int(_PID_PATH.read_text().strip())
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass
    _PID_PATH.unlink(missing_ok=True)


def _start_watcher() -> None:
    subprocess.Popen(
        [sys.executable, "-m", "pimer.watcher"],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
_TAB_IDS    = ["tab-timers", "tab-alarms", "tab-stopwatches"]
_TAB_TITLES = ["Timers (1)", "Alarms (2)", "Stopwatches (3)"]


def _detect_terminal_bg() -> str | None:
    """Query the terminal background color via OSC 11 before Textual takes the tty."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return None
    try:
        import select
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            os.write(1, b"\033]11;?\007")
            buf = b""
            timeout = 0.2
            while select.select([fd], [], [], timeout)[0]:
                buf += os.read(fd, 64)
                if buf.endswith(b"\007") or b"\033\\" in buf:
                    break
                timeout = 0.05
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        m = re.search(rb"rgb:([0-9a-fA-F]+)/([0-9a-fA-F]+)/([0-9a-fA-F]+)", buf)
        if m:
            r = int(m.group(1)[:2], 16)
            g = int(m.group(2)[:2], 16)
            b = int(m.group(3)[:2], 16)
            return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        pass
    return None


class PimerApp(App):
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("q",         "quit",            "Quit",        show=True),
        Binding("1",         "switch_tab(0)",   "Timers",      show=False),
        Binding("2",         "switch_tab(1)",   "Alarms",      show=False),
        Binding("3",         "switch_tab(2)",   "Stopwatches", show=False),
    ]

    def __init__(self, terminal_bg: str | None = None) -> None:
        super().__init__()
        self._terminal_bg = terminal_bg
        self.store = Store()
        self.store.load()

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="main-pane"):
            with TabbedContent(id="tabs"):
                for kind, tab_id, title in zip(_KINDS, _TAB_IDS, _TAB_TITLES):
                    with TabPane(title, id=tab_id):
                        yield BigTimerWidget(id=f"big-{kind.value}")
                        yield ItemListWidget(kind=kind, id=f"list-{kind.value}")
        yield Footer()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        _kill_watcher()
        self.theme = "textual-light"
        if self._terminal_bg:
            bg = Color.parse(self._terminal_bg)
            self.screen.styles.background = bg
        self._refresh_lists()
        self.set_interval(0.5, self._tick)
        self._active_list().focus()

    def on_unmount(self) -> None:
        if any(it.state == ItemState.RUNNING for it in self.store.items):
            _start_watcher()

    # ── Tick ──────────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        fired = self.store.tick()
        for item in fired:
            label = "alarm" if item.kind == ItemKind.ALARM else "timer"
            notify.fire(f"{item.name} {label} finished")
        if fired:
            self._refresh_lists()
            return
        for kind in _KINDS:
            if any(it.state == ItemState.RUNNING for it in self.store.get_by_kind(kind)):
                self.query_one(f"#list-{kind.value}", ItemListWidget).set_items(self.store.items)
        self._sync_big_displays()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _refresh_lists(self) -> None:
        for kind in _KINDS:
            self.query_one(f"#list-{kind.value}", ItemListWidget).set_items(self.store.items)
        self._sync_big_displays()

    def _sync_big_displays(self) -> None:
        """Refresh each tab's big display; hide it when the tab has no items."""
        for kind in _KINDS:
            list_w = self.query_one(f"#list-{kind.value}", ItemListWidget)
            big_w  = self.query_one(f"#big-{kind.value}", BigTimerWidget)
            if big_w._item is not None:
                item = self.store.get_by_id(big_w._item.id)
            else:
                item = list_w._selected()
            big_w.set_item(item)
            big_w.display = item is not None

    def _active_kind(self) -> ItemKind:
        tabs = self.query_one("#tabs", TabbedContent)
        active_id = tabs.active or _TAB_IDS[0]
        try:
            return _KINDS[_TAB_IDS.index(active_id)]
        except ValueError:
            return _KINDS[0]

    def _active_list(self) -> ItemListWidget:
        return self.query_one(f"#list-{self._active_kind().value}", ItemListWidget)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_switch_tab(self, index: int) -> None:
        self.query_one("#tabs", TabbedContent).active = _TAB_IDS[index]
        self.query_one(f"#list-{_KINDS[index].value}", ItemListWidget).focus()

    # ── Message handlers ──────────────────────────────────────────────────────

    def on_item_list_widget_selection_changed(
        self, message: ItemListWidget.SelectionChanged
    ) -> None:
        big_w = self.query_one(f"#big-{message.kind.value}", BigTimerWidget)
        big_w.set_item(message.item)
        big_w.display = message.item is not None

    def on_item_list_widget_new_requested(
        self, _message: ItemListWidget.NewRequested
    ) -> None:
        kind = self._active_kind()

        def on_result(result: dict | None) -> None:
            self._active_list().focus()
            if result is None:
                return
            item = Item(kind=kind, **result)
            if kind == ItemKind.ALARM:
                item.state = ItemState.RUNNING
            self.store.add(item)
            self._refresh_lists()

        self.push_screen(FormScreen(kind=kind), on_result)

    def on_item_list_widget_edit_requested(
        self, message: ItemListWidget.EditRequested
    ) -> None:
        item = message.item
        edit_data = {
            "name":          item.name,
            "duration_secs": item.duration_secs,
            "target_at":     item.target_at,
        }

        def on_result(result: dict | None) -> None:
            self._active_list().focus()
            if result is None:
                return
            item.name = result["name"]
            if item.kind == ItemKind.TIMER:
                item.duration_secs = result["duration_secs"]
                item.elapsed_secs  = min(item.elapsed_secs, item.duration_secs)
            elif item.kind == ItemKind.ALARM:
                item.target_at       = result["target_at"]
                item.target_datetime = result["target_datetime"]
            self.store.update(item)
            self._refresh_lists()

        self.push_screen(FormScreen(kind=item.kind, edit_item=edit_data), on_result)

    def on_item_list_widget_delete_requested(
        self, message: ItemListWidget.DeleteRequested
    ) -> None:
        kind  = message.item.kind
        big_w = self.query_one(f"#big-{kind.value}", BigTimerWidget)
        if big_w._item and big_w._item.id == message.item.id:
            big_w.set_item(None)
            big_w.display = False
        self.store.delete(message.item.id)
        self._refresh_lists()

    def on_item_list_widget_toggle_requested(
        self, message: ItemListWidget.ToggleRequested
    ) -> None:
        item = message.item
        if item.kind == ItemKind.ALARM:
            return
        if item.state == ItemState.RUNNING:
            item.state = ItemState.PAUSED
        elif item.state in (ItemState.IDLE, ItemState.PAUSED):
            item.state = ItemState.RUNNING
        self.store.update(item)
        self._refresh_lists()

    def on_item_list_widget_reset_requested(
        self, message: ItemListWidget.ResetRequested
    ) -> None:
        item = message.item
        item.elapsed_secs = 0.0
        if item.kind == ItemKind.ALARM:
            rearm_alarm(item)
        else:
            item.state = ItemState.IDLE
        self.store.update(item)
        self._refresh_lists()


def main() -> None:
    PimerApp(terminal_bg=_detect_terminal_bg()).run()
