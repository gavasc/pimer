# pimer

Terminal-based timer, alarm, and stopwatch app built with [Textual](https://textual.textualize.io/).

## Features

- **Timers** — countdown with name and duration (e.g. `5m30s`, `1h`)
- **Alarms** — set a 24h time (HH:MM), wraps to next day if past
- **Stopwatch** — simple elapsed-time counter
- Persistent state across sessions (saved to `~/.local/share/pimer/state.json`)
- Desktop notifications via `notify-send` + alarm sound via `ffplay`/`paplay`
- Background daemon — running timers/alarms still fire even when the TUI is closed

## Install

```sh
pip install .
# or
uv tool install .
```

Or run directly without installing:

```sh
python pimer.py
# or
uv run pimer.py
```

Requires Python >= 3.11 and `textual >= 0.87`.

## Usage

```
Key          Action
─────────────────────
1 / 2 / 3       Switch tab (Timers / Alarms / Stopwatches)
n               Create a new item
Enter/Space     Start / pause the selected item
r               Reset the selected item
d               Delete the selected item
j / ↓           Move selection down
k / ↑           Move selection up
q               Quit
```
