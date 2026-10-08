"""
The Viator terminal dashboard: module status on top, live log underneath.

Reads `/viator/node_status` for the status pane and `/rosout` for the log pane. Taking the
log from `/rosout` rather than parsing a terminal means the fields arrive already
structured, so the four nested bracket prefixes the console used to print are a rendering
choice here instead of something to strip.

One thing `/rosout` cannot show: output that never went through a ROS logger, such as a
Python traceback or OpenCV's own C++ warnings. Those only exist on the launch's own stdout,
which `make launch` puts in `log/launch-latest.log` and a deployed rover puts in the
journal (`journalctl -u viator -f`). `?` shows the path in use.
"""

import base64
import os
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from rcl_interfaces.msg import Log
from rich.markup import escape
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Input, RichLog, Static

from custom_interfaces.msg import NodeStatus
from lib.status import STATE_NAMES

from .bridge import LogRecord, RosBridge, StatusRecord

# Levels the `f` key cycles through, as a minimum threshold.
LEVEL_CYCLE = [Log.DEBUG, Log.INFO, Log.WARN, Log.ERROR]

LEVEL_LABELS = {
    Log.DEBUG: "debug+",
    Log.INFO: "info+",
    Log.WARN: "warn+",
    Log.ERROR: "error",
}

LEVEL_STYLES = {
    Log.DEBUG: "dim",
    Log.INFO: "green",
    Log.WARN: "yellow",
    Log.ERROR: "bold red",
    Log.FATAL: "bold white on red",
}

STATE_STYLES = {
    NodeStatus.STARTING: "cyan",
    NodeStatus.OK: "green",
    NodeStatus.DEGRADED: "yellow",
    NodeStatus.FAILED: "bold red",
}

# Enough history to scroll back through a run without growing without bound.
BUFFER_SIZE = 5000

# Matches the supervisor: a module republishes every second, so three misses means gone.
STALE_AFTER_SEC = 3.0

SAVE_DIR = Path.home() / ".ros" / "viator-tui"

# Where the launch's own stdout went, if whatever started us said so. Set by scripts/run.sh.
LAUNCH_LOG_HINT = os.environ.get("VIATOR_LAUNCH_LOG", "log/launch-latest.log")

HELP_TEXT = f"""[bold]keys[/bold]
  [cyan]p[/cyan]  pause the log, so you can read it. nothing is lost while paused
  [cyan]f[/cyan]  cycle the minimum severity: info+ -> warn+ -> error -> debug+
  [cyan]/[/cyan]  filter the log by text. enter applies it, esc clears it
  [cyan]c[/cyan]  copy every visible line to your clipboard, local machine included
  [cyan]s[/cyan]  save every visible line under ~/.ros/viator-tui
  [cyan]?[/cyan]  this
  [cyan]q[/cyan]  quit

[bold]module states[/bold]
  [cyan]starting[/cyan]  constructed, but hasn't finished bringing itself up
  [green]ok[/green]        started and doing its job
  [yellow]degraded[/yellow]  running, but something is wrong. the detail says what
  [bold red]failed[/bold red]    running, but can't do its job at all
  [bold red]stale[/bold red]     stopped reporting for {int(STALE_AFTER_SEC)}s, so it died or hung

[bold]what this can't show[/bold]
  the log pane is [cyan]/rosout[/cyan], so it has everything logged through ROS
  and nothing that bypassed it. a python traceback or OpenCV's own
  warnings only reach the launch's stdout:
    [cyan]{LAUNCH_LOG_HINT}[/cyan]

[dim]? or esc to close[/dim]"""


def _copyToClipboard(app: App[None], text: str) -> str:
    """
    Copies text to the clipboard the operator is actually sitting at.

    Over SSH that has to be the local machine, not the rover, so this goes through OSC 52:
    the terminal emulator intercepts the escape sequence and does the copy at its end.
    Textual's own helper handles tmux wrapping, so prefer it when the installed version
    has it and fall back to writing the sequence directly.
    """
    copier = getattr(app, "copy_to_clipboard", None)
    if callable(copier):
        copier(text)
        return "copied to clipboard"

    payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
    sys.stdout.write(f"\x1b]52;c;{payload}\x07")
    sys.stdout.flush()
    return "copied to clipboard (osc52)"


class ViatorTui(App[None]):
    """
    The dashboard application.
    """

    TITLE = "viator"

    CSS = """
    Screen {
        layout: vertical;
        layers: base overlay;
    }

    #status {
        height: auto;
        max-height: 12;
        border: round $accent;
        border-title-align: left;
        padding: 0 1;
    }

    #log-pane {
        border: round $accent;
        border-title-align: left;
    }

    #log {
        padding: 0 1;
    }

    #search {
        display: none;
        border: none;
        height: 1;
    }

    #search.visible {
        display: block;
    }

    #help {
        layer: overlay;
        display: none;
        width: auto;
        max-width: 80;
        height: auto;
        max-height: 100%;
        border: round $accent;
        border-title-align: left;
        background: $surface;
        padding: 1 2;
        offset: 3 1;
    }

    #help.visible {
        display: block;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "quit"),
        Binding("p", "toggle_pause", "pause"),
        Binding("f", "cycle_level", "level"),
        Binding("slash", "focus_search", "search"),
        Binding("c", "copy", "copy"),
        Binding("s", "save", "save"),
        Binding("question_mark", "toggle_help", "help"),
        Binding("escape", "dismiss_overlays", "clear", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()

        self._records: deque[LogRecord] = deque(maxlen=BUFFER_SIZE)
        self._status: dict[str, StatusRecord] = {}
        self._status_seen: dict[str, float] = {}

        self._paused = False
        self._level_index = LEVEL_CYCLE.index(Log.INFO)
        self._search = ""

        self._bridge = RosBridge(on_status=self._handleStatus, on_log=self._handleLog)

    # ***************
    # Composition and lifecycle
    # ***************
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        table: DataTable[Text] = DataTable(id="status", cursor_type="none", zebra_stripes=False)
        table.border_title = "modules"
        yield table

        with Vertical(id="log-pane") as pane:
            pane.border_title = "log"
            yield Input(placeholder="filter text, enter to apply", id="search")
            yield RichLog(id="log", markup=True, wrap=True, highlight=False, auto_scroll=True)

        help_panel = Static(HELP_TEXT, id="help")
        help_panel.border_title = "how to read this"
        yield help_panel

        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#status", DataTable)
        table.add_columns("module", "state", "detail")

        self._bridge.start()
        self.set_interval(1.0, self._refreshStatus)
        self._updateTitles()

    def on_unmount(self) -> None:
        self._bridge.stop()

    # ***************
    # Callbacks from the rclpy thread
    # ***************
    def _handleStatus(self, record: StatusRecord) -> None:
        """
        Called on the rclpy thread, so hand the work back to the UI thread.
        """
        self.call_from_thread(self._applyStatus, record)

    def _handleLog(self, record: LogRecord) -> None:
        self.call_from_thread(self._applyLog, record)

    def _applyStatus(self, record: StatusRecord) -> None:
        self._status[record.name] = record
        self._status_seen[record.name] = time.monotonic()
        self._refreshStatus()

    def _applyLog(self, record: LogRecord) -> None:
        self._records.append(record)
        if not self._paused and self._shouldShow(record):
            self.query_one("#log", RichLog).write(self._renderRecord(record))

    # ***************
    # Rendering
    # ***************
    def _shouldShow(self, record: LogRecord) -> bool:
        """
        Whether a record passes the level threshold and the text filter.
        """
        if record.level < LEVEL_CYCLE[self._level_index]:
            return False
        if self._search and self._search.lower() not in record.message.lower():
            return False
        return True

    def _renderRecord(self, record: LogRecord) -> str:
        """
        One log line. The message is escaped so log text can't be read as rich markup.
        """
        style = LEVEL_STYLES.get(record.level, "white")
        return (
            f"[dim]{record.clock}[/dim] "
            f"[{style}]{record.level_name:<5}[/{style}] "
            f"[cyan]{escape(record.node)}[/cyan]  {escape(record.message)}"
        )

    def _redrawLog(self) -> None:
        """
        Rewrites the whole pane from the buffer, for when a filter changes.
        """
        pane = self.query_one("#log", RichLog)
        pane.clear()
        for record in self._records:
            if self._shouldShow(record):
                pane.write(self._renderRecord(record))

    def _refreshStatus(self) -> None:
        """
        Rebuilds the status table. Cheap: there are only ever a handful of rows.
        """
        table = self.query_one("#status", DataTable)
        table.clear()

        now = time.monotonic()
        for name in sorted(self._status):
            record = self._status[name]
            if now - self._status_seen.get(name, 0.0) > STALE_AFTER_SEC:
                state = Text("stale", style="bold red")
            else:
                state = Text(
                    STATE_NAMES.get(record.state, "unknown"),
                    style=STATE_STYLES.get(record.state, "white"),
                )
            table.add_row(Text(name), state, Text(record.detail))

        self._updateTitles()

    def _updateTitles(self) -> None:
        """
        Keeps the pane borders showing the current filter and pause state.
        """
        level = LEVEL_LABELS[LEVEL_CYCLE[self._level_index]]
        bits = [f"log  {level}"]
        if self._search:
            bits.append(f'"{self._search}"')
        if self._paused:
            bits.append("PAUSED")
        self.query_one("#log-pane", Vertical).border_title = "  ".join(bits)

        self.query_one(
            "#status", DataTable
        ).border_title = f"modules  {len(self._status)} reporting"

    # ***************
    # Actions
    # ***************
    def action_toggle_pause(self) -> None:
        """
        Freezes the log pane. A log this fast is unreadable while it's moving.
        """
        self._paused = not self._paused
        pane = self.query_one("#log", RichLog)
        pane.auto_scroll = not self._paused
        if not self._paused:
            self._redrawLog()
        self._updateTitles()

    def action_cycle_level(self) -> None:
        """
        Steps the minimum severity shown.
        """
        self._level_index = (self._level_index + 1) % len(LEVEL_CYCLE)
        self._redrawLog()
        self._updateTitles()

    def action_focus_search(self) -> None:
        """
        Reveals and focuses the text filter.
        """
        search = self.query_one("#search", Input)
        search.add_class("visible")
        search.focus()

    def action_toggle_help(self) -> None:
        """
        Shows what the keys do and what the states mean.

        The footer lists the keys but not what any of them are for, and the status column
        is four words that only make sense if you already know them. This is the answer to
        "I opened the dashboard, now what".
        """
        self.query_one("#help", Static).toggle_class("visible")

    def action_clear_search(self) -> None:
        """
        Drops the text filter and hides the input again.
        """
        search = self.query_one("#search", Input)
        search.value = ""
        search.remove_class("visible")
        self._search = ""
        self._redrawLog()
        self._updateTitles()
        self.query_one("#log", RichLog).focus()

    def action_dismiss_overlays(self) -> None:
        """
        What escape does: close the help panel if it's open, otherwise drop the filter.

        One key for "get me back to the log" rather than one per thing that could be
        covering it.
        """
        help_panel = self.query_one("#help", Static)
        if help_panel.has_class("visible"):
            help_panel.remove_class("visible")
            return
        self.action_clear_search()

    def action_copy(self) -> None:
        """
        Copies everything currently visible in the log pane.
        """
        text = "\n".join(
            f"{r.clock} {r.level_name:<5} {r.node}  {r.message}"
            for r in self._records
            if self._shouldShow(r)
        )
        if not text:
            self.notify("nothing to copy", severity="warning")
            return
        self.notify(_copyToClipboard(self, text))

    def action_save(self) -> None:
        """
        Writes the visible log to a file on the rover.

        The clipboard is convenient but a file is the thing you still have after a failed
        run, so both exist.
        """
        lines = [
            f"{r.clock} {r.level_name:<5} {r.node}  {r.message}"
            for r in self._records
            if self._shouldShow(r)
        ]
        if not lines:
            self.notify("nothing to save", severity="warning")
            return

        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        path = SAVE_DIR / f"viator-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
        path.write_text("\n".join(lines) + "\n")
        self.notify(f"saved {len(lines)} lines to {path}")

    # ***************
    # Widget events
    # ***************
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._search = event.value.strip()
        self._redrawLog()
        self._updateTitles()
        self.query_one("#log", RichLog).focus()


def main() -> None:
    """
    The entry point of the dashboard.
    """
    ViatorTui().run()


if __name__ == "__main__":
    main()
