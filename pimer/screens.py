from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from .models import ItemKind, parse_alarm_time, parse_duration, secs_to_human


class FormScreen(ModalScreen):
    DEFAULT_CSS = """
    FormScreen {
        align: center middle;
    }
    #dialog {
        width: 52;
        height: auto;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    #title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    .field-label {
        width: 16;
        height: 3;
        content-align: left middle;
        color: $text-muted;
    }
    .field-row {
        height: 3;
    }
    #error {
        color: $error;
        margin-top: 1;
        display: none;
    }
    #error.visible {
        display: block;
    }
    #help {
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        kind: ItemKind,
        edit_item: dict | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.kind = kind
        self.edit_item = edit_item

    def compose(self) -> ComposeResult:
        mode  = "Edit" if self.edit_item else "New"
        title = f"{mode} {self.kind.value.capitalize()}"
        with Vertical(id="dialog"):
            yield Static(title, id="title")
            with Horizontal(classes="field-row"):
                yield Label("Name:", classes="field-label")
                yield Input(
                    value=self.edit_item.get("name", "") if self.edit_item else "",
                    placeholder="e.g. Tea",
                    id="input-name",
                )
            if self.kind == ItemKind.TIMER:
                dur_val = ""
                if self.edit_item:
                    dur_val = secs_to_human(self.edit_item.get("duration_secs", 0))
                with Horizontal(classes="field-row"):
                    yield Label("Duration:", classes="field-label")
                    yield Input(
                        value=dur_val,
                        placeholder="e.g. 5m30s or 1h",
                        id="input-duration",
                    )
            elif self.kind == ItemKind.ALARM:
                with Horizontal(classes="field-row"):
                    yield Label("Time (HH:MM):", classes="field-label")
                    yield Input(
                        value=self.edit_item.get("target_at", "") if self.edit_item else "",
                        placeholder="HH:MM",
                        id="input-time",
                    )
            yield Static("", id="error")
            yield Static("Tab: next   Enter: save   Esc: cancel", id="help")

    def on_mount(self) -> None:
        self.query_one("#input-name", Input).focus()
        if terminal_bg := getattr(self.app, "_terminal_bg", None):
            from textual.color import Color
            bg = Color.parse(terminal_bg)
            self.query_one("#dialog").styles.background = bg
            for inp in self.query("Input"):
                inp.styles.background = bg

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.stop()
        elif event.key == "enter":
            self._submit()
            event.stop()

    def _submit(self) -> None:
        name = self.query_one("#input-name", Input).value.strip()
        if not name:
            self._show_error("Name cannot be empty")
            return

        result: dict = {"name": name}

        if self.kind == ItemKind.TIMER:
            raw = self.query_one("#input-duration", Input).value.strip()
            try:
                result["duration_secs"] = parse_duration(raw)
            except ValueError as exc:
                self._show_error(str(exc))
                return

        elif self.kind == ItemKind.ALARM:
            raw = self.query_one("#input-time", Input).value.strip()
            try:
                target_dt = parse_alarm_time(raw)
            except ValueError:
                self._show_error(f"Invalid time {raw!r} — use HH:MM (24h)")
                return
            result["target_at"]       = raw
            result["target_datetime"] = target_dt.isoformat()

        self.dismiss(result)

    def _show_error(self, msg: str) -> None:
        err = self.query_one("#error", Static)
        err.update(msg)
        err.add_class("visible")
