"""
The Viator tui: module status on top, live log and CAN traffic underneath.

The log follows the launch-output file as well as /rosout, so startup output, tracebacks
and native-library warnings are there even when the tui opens late.
"""

import base64
import os
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, RichLog, Static

from custom_interfaces.msg import NodeStatus
from lib.status import STATE_NAMES

from .bridge import (
    CAN_IFACE,
    LEVEL_DEBUG,
    LEVEL_ERROR,
    LEVEL_FATAL,
    LEVEL_INFO,
    LEVEL_WARN,
    CanFrame,
    LogRecord,
    RosBridge,
    StatusRecord,
)

LEVEL_CYCLE = [LEVEL_DEBUG, LEVEL_INFO, LEVEL_WARN, LEVEL_ERROR]

LEVEL_LABELS = {
    LEVEL_DEBUG: "debug+",
    LEVEL_INFO: "info+",
    LEVEL_WARN: "warn+",
    LEVEL_ERROR: "error",
}

# a gutter rather than the level's name: four hundred lines of `INFO` is four hundred
# repetitions of the least interesting thing on each one
LEVEL_GUTTER = {
    LEVEL_DEBUG: ("┊", "dim"),
    LEVEL_INFO: ("│", "dim"),
    LEVEL_WARN: ("┃", "yellow"),
    LEVEL_ERROR: ("┃", "bold red"),
    LEVEL_FATAL: ("┃", "bold white on red"),
}

MESSAGE_STYLES = {
    LEVEL_DEBUG: "dim",
    LEVEL_WARN: "yellow",
    LEVEL_ERROR: "red",
    LEVEL_FATAL: "bold red",
}

STATE_STYLES = {
    NodeStatus.STARTING: "cyan",
    NodeStatus.OK: "green",
    NodeStatus.DEGRADED: "yellow",
    NodeStatus.FAILED: "bold red",
}

STALE_STYLE = "bold red"

# picked from the id itself, so a motor keeps its colour all run and the pattern of six
# visibly breaks when one of them stops answering
BUS_ID_STYLES = ("cyan", "magenta", "green", "blue", "bright_cyan", "bright_magenta")

NODE_WIDTH = 15

# `HH:MM:SS`, the gutter, the module, and a space
PREFIX_WIDTH = 8 + 3 + NODE_WIDTH + 1

BUFFER_SIZE = 5000

# the bus pane is a window on live traffic, not a record of it
BUS_BUFFER_SIZE = 500

# frames arrive faster than a terminal can redraw, so the pane gets the latest frame per
# id a few times a second rather than a backlog
BUS_DRAIN_PERIOD_SEC = 0.25
BUS_DISPLAY_LIMIT = 12

# often enough to read as live, rarely enough that a burst of startup output is one
# redraw instead of two hundred
DRAIN_PERIOD_SEC = 0.1

# matches the supervisor: a module republishes every second, so three misses means gone
STALE_AFTER_SEC = 3.0

SAVE_DIR = Path.home() / ".ros" / "viator-tui"

# where the launch's own stdout went, if whatever started us said so
LAUNCH_LOG_HINT = os.environ.get("VIATOR_LAUNCH_LOG", "log/launch-latest.log")

HELP_TEXT = f"""[bold]keys[/bold]
  [cyan]p[/cyan]  pause the log, so you can read it. nothing is lost while paused
  [cyan]f[/cyan]  cycle the minimum severity: info+ -> warn+ -> error -> debug+
  [cyan]/[/cyan]  filter the log by text. enter applies it, esc clears it
  [cyan]b[/cyan]  show or hide the bus pane, to give the log the full width
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

[bold]the panes[/bold]
  [cyan]modules[/cyan]  what each module says about itself, once a second
  [cyan]log[/cyan]      the launch output: ROS logs, tracebacks, native warnings
             [dim]{LAUNCH_LOG_HINT}[/dim]
  [cyan]{CAN_IFACE:<8}[/cyan] raw frames on the bus, as candump sees them. an empty pane
             with healthy modules means nothing is reaching the wire

[dim]? or esc to close[/dim]"""


def _copyToClipboard(app: App[None], text: str) -> str:
    # over SSH the clipboard that matters is the operator's, not the rover's, so this
    # goes through OSC 52 and lets their terminal emulator do the copy
    copier = getattr(app, "copy_to_clipboard", None)
    if callable(copier):
        copier(text)
        return "copied to clipboard"

    payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
    sys.stdout.write(f"\x1b]52;c;{payload}\x07")
    sys.stdout.flush()
    return "copied to clipboard (osc52)"


def shortNodeName(name: str) -> str:
    # `/can_rmdx8_node` is `can_rmdx8`
    short = name.lstrip("/").rsplit("/", 1)[-1]
    if short.endswith("_node"):
        short = short[: -len("_node")]
    if len(short) > NODE_WIDTH:
        return short[: NODE_WIDTH - 1] + "…"
    return short


class ViatorTui(App[None]):
    TITLE = "viator"

    # the one theme whose colours are the terminal's own, so the tui sits in the
    # operator's terminal rather than painting over it
    THEME = "ansi-dark"

    CSS = """
    Screen {
        layout: vertical;
        layers: base overlay;
        background: transparent;
    }

    /* nothing below here paints a surface of its own */
    Header, HeaderIcon, HeaderTitle, HeaderClock, HeaderClockSpace,
    Footer, FooterKey, DataTable, RichLog, Input, Vertical, Horizontal {
        background: transparent;
    }

    FooterKey .footer-key--key, FooterKey .footer-key--description {
        background: transparent;
    }

    DataTable .datatable--header, DataTable .datatable--odd-row,
    DataTable .datatable--even-row, DataTable .datatable--cursor,
    DataTable .datatable--hover {
        background: transparent;
    }

    DataTable .datatable--header {
        text-style: dim;
    }

    RichLog, DataTable {
        scrollbar-background: transparent;
        scrollbar-background-hover: transparent;
        scrollbar-background-active: transparent;
        scrollbar-size: 1 1;
    }

    #status {
        height: auto;
        max-height: 14;
        border: round $border;
        border-title-align: left;
        border-subtitle-align: right;
        padding: 0 1;
    }

    #panes {
        height: 1fr;
    }

    #log-pane {
        width: 1fr;
        border: round $border;
        border-title-align: left;
        border-subtitle-align: right;
    }

    #log {
        padding: 0 1;
        overflow-x: hidden;
    }

    #bus-pane {
        width: 38;
        border: round $border;
        border-title-align: left;
        border-subtitle-align: right;
    }

    #bus-pane.hidden {
        display: none;
    }

    #bus {
        padding: 0 1;
        overflow-x: hidden;
        /* a live feed, not a document: there is nothing to scroll back to */
        scrollbar-size-vertical: 0;
    }

    #search {
        display: none;
        border: none;
        height: 1;
        padding: 0 1;
    }

    #search.visible {
        display: block;
    }

    /* the one opaque thing in here: it covers the log while it is open */
    #help {
        layer: overlay;
        display: none;
        width: auto;
        max-width: 80;
        height: auto;
        max-height: 100%;
        border: round $border;
        border-title-align: left;
        background: ansi_black;
        padding: 1 2;
        offset: 3 1;
    }

    #help.visible {
        display: block;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "quit"),
        Binding("p", "toggle_pause", "pause"),
        Binding("f", "cycle_level", "level"),
        Binding("slash", "focus_search", "search"),
        Binding("b", "toggle_bus", "bus"),
        Binding("c", "copy", "copy"),
        Binding("s", "save", "save"),
        Binding("question_mark", "toggle_help", "help"),
        Binding("escape", "dismiss_overlays", "clear", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()

        self._records: deque[LogRecord] = deque(maxlen=BUFFER_SIZE)
        self._recent_log_keys: dict[tuple[int, str, str], float] = {}
        self._status: dict[str, StatusRecord] = {}
        self._status_seen: dict[str, float] = {}

        # the bridge's threads only ever append here; everything that touches a widget
        # happens on the drain timers, on the ui thread
        self._pending_lock = threading.Lock()
        self._pending_logs: deque[LogRecord] = deque(maxlen=BUFFER_SIZE)
        self._pending_status: list[StatusRecord] = []
        self._bus_pending: deque[CanFrame] = deque(maxlen=BUS_BUFFER_SIZE)
        self._bus_received = 0
        self._bus_ids: set[str] = set()
        self._bus_count = 0
        self._bus_rate = 0
        self._bus_state = "waiting"

        self._paused = False
        self._level_index = LEVEL_CYCLE.index(LEVEL_INFO)
        self._search = ""

        self._bridge = RosBridge(
            on_status=self._handleStatus,
            on_log=self._handleLog,
            launch_log=Path(LAUNCH_LOG_HINT),
            on_frame=self._handleFrame,
            on_bus_state=self._handleBusState,
        )

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, icon="●")

        table: DataTable[Text] = DataTable(id="status", cursor_type="none", zebra_stripes=False)
        table.border_title = "modules"
        yield table

        with Horizontal(id="panes"):
            with Vertical(id="log-pane") as log_pane:
                log_pane.border_title = "log"
                yield Input(placeholder="filter text, enter to apply", id="search")
                yield RichLog(id="log", wrap=True, highlight=False, auto_scroll=True, min_width=0)

            with Vertical(id="bus-pane") as bus_pane:
                bus_pane.border_title = CAN_IFACE
                yield RichLog(
                    id="bus",
                    wrap=False,
                    highlight=False,
                    auto_scroll=True,
                    min_width=0,
                    max_lines=BUS_BUFFER_SIZE,
                )

        help_panel = Static(HELP_TEXT, id="help", markup=True)
        help_panel.border_title = "how to read this"
        yield help_panel

        yield Footer()

    def on_mount(self) -> None:
        self.theme = self.THEME

        table = self.query_one("#status", DataTable)
        table.add_columns("module", "state", "detail")

        self._bridge.start()
        self.set_interval(1.0, self._refreshStatus)
        self.set_interval(1.0, self._refreshBusRate)
        self.set_interval(DRAIN_PERIOD_SEC, self._drainRecords)
        self.set_interval(BUS_DRAIN_PERIOD_SEC, self._drainBus)
        self._updateTitles()

    def on_unmount(self) -> None:
        self._bridge.stop()

    # the four `_handle` methods below run on the bridge's threads. They queue rather
    # than call `call_from_thread`, which blocks its caller until the event loop gets
    # round to it: a thread parked in there when the app starts unmounting deadlocks
    # against the shutdown, which is how quitting during the startup burst used to wedge
    def _handleStatus(self, record: StatusRecord) -> None:
        with self._pending_lock:
            self._pending_status.append(record)

    def _handleLog(self, record: LogRecord) -> None:
        with self._pending_lock:
            self._pending_logs.append(record)

    def _handleBusState(self, state: str) -> None:
        self._bus_state = state

    def _handleFrame(self, frame: CanFrame) -> None:
        with self._pending_lock:
            self._bus_pending.append(frame)
            self._bus_received += 1

    def _applyStatus(self, record: StatusRecord) -> None:
        self._status[record.name] = record
        self._status_seen[record.name] = time.monotonic()
        self._refreshStatus()

    def _applyLog(self, record: LogRecord) -> None:
        key = (record.level, record.node, record.message)
        now = time.monotonic()
        if now - self._recent_log_keys.get(key, 0.0) < 1.0:
            return
        self._recent_log_keys[key] = now
        if len(self._recent_log_keys) > BUFFER_SIZE:
            self._recent_log_keys = {
                old_key: seen for old_key, seen in self._recent_log_keys.items() if now - seen < 1.0
            }
        self._records.append(record)
        if not self._paused and self._shouldShow(record):
            self.query_one("#log", RichLog).write(self._renderRecord(record))

    def _drainRecords(self) -> None:
        with self._pending_lock:
            statuses = self._pending_status
            logs = list(self._pending_logs)
            self._pending_status = []
            self._pending_logs.clear()

        for status in statuses:
            self._applyStatus(status)
        for record in logs:
            self._applyLog(record)

    def _drainBus(self) -> None:
        # the bus runs at thousands of frames a second with the drivebase moving, so the
        # pane shows the latest frame per id rather than an ever-growing backlog, and
        # every frame is still counted for the rate in the title
        with self._pending_lock:
            frames = list(self._bus_pending)
            self._bus_pending.clear()
            received = self._bus_received
            self._bus_received = 0

        if not frames:
            return

        pane = self.query_one("#bus", RichLog)
        latest_by_id: dict[str, CanFrame] = {}
        for frame in frames:
            self._bus_ids.add(frame.can_id)
            latest_by_id.pop(frame.can_id, None)
            latest_by_id[frame.can_id] = frame

        self._bus_count += received or len(frames)
        if not self._paused:
            for frame in list(latest_by_id.values())[-BUS_DISPLAY_LIMIT:]:
                pane.write(self._renderFrame(frame))

    def _shouldShow(self, record: LogRecord) -> bool:
        if record.level < LEVEL_CYCLE[self._level_index]:
            return False
        if self._search and self._search.lower() not in record.message.lower():
            return False
        return True

    def _renderRecord(self, record: LogRecord) -> Table:
        # a two column grid rather than one string, so a long message wraps under itself
        # instead of breaking the column of timestamps that makes the log scannable
        glyph, glyph_style = LEVEL_GUTTER.get(record.level, ("│", "dim"))
        prefix = Text.assemble(
            (record.clock, "dim"),
            " ",
            (glyph, glyph_style),
            " ",
            (shortNodeName(record.node), "cyan"),
        )

        line = Table.grid(expand=True)
        line.add_column(width=PREFIX_WIDTH, no_wrap=True)
        line.add_column(ratio=1, overflow="fold")
        line.add_row(prefix, Text(record.message, style=MESSAGE_STYLES.get(record.level, "")))
        return line

    def _renderFrame(self, frame: CanFrame) -> Text:
        try:
            style = BUS_ID_STYLES[int(frame.can_id, 16) % len(BUS_ID_STYLES)]
        except ValueError:
            style = "cyan"
        return Text.assemble(
            (frame.can_id.rjust(3), style),
            (f" {frame.dlc} ", "dim"),
            frame.data,
        )

    def _redrawLog(self) -> None:
        pane = self.query_one("#log", RichLog)
        pane.clear()
        for record in self._records:
            if self._shouldShow(record):
                pane.write(self._renderRecord(record))

    def _refreshStatus(self) -> None:
        table = self.query_one("#status", DataTable)
        table.clear()

        now = time.monotonic()
        for name in sorted(self._status):
            record = self._status[name]
            if now - self._status_seen.get(name, 0.0) > STALE_AFTER_SEC:
                label, style = "stale", STALE_STYLE
            else:
                label = STATE_NAMES.get(record.state, "unknown")
                style = STATE_STYLES.get(record.state, "white")

            module = Text.assemble(("● ", style), name)
            table.add_row(module, Text(label, style=style), Text(record.detail, style="dim"))

        self._updateTitles()

    def _refreshBusRate(self) -> None:
        self._bus_rate = self._bus_count
        self._bus_count = 0
        self._updateTitles()

    def _statusSummary(self) -> Text:
        now = time.monotonic()
        healthy = sum(
            1
            for name, record in self._status.items()
            if record.state == NodeStatus.OK
            and now - self._status_seen.get(name, 0.0) <= STALE_AFTER_SEC
        )
        total = len(self._status)
        if not total:
            return Text("waiting for reports", style="dim")
        style = "green" if healthy == total else "yellow"
        return Text(f"{healthy}/{total} ok", style=style)

    def _updateTitles(self) -> None:
        status = self.query_one("#status", DataTable)
        status.border_subtitle = self._statusSummary()

        log_pane = self.query_one("#log-pane", Vertical)
        log_pane.border_title = f"log  {LEVEL_LABELS[LEVEL_CYCLE[self._level_index]]}"
        state = []
        if self._search:
            state.append(f'"{self._search}"')
        if self._paused:
            state.append("paused")
        log_pane.border_subtitle = "  ".join(state)

        bus_pane = self.query_one("#bus-pane", Vertical)
        if self._bus_state:
            bus_pane.border_subtitle = Text(self._bus_state, style="dim")
        else:
            bus_pane.border_subtitle = Text(
                f"{self._bus_rate}/s  {len(self._bus_ids)} ids",
                style="dim" if self._bus_rate else "yellow",
            )

    def action_toggle_pause(self) -> None:
        self._paused = not self._paused
        pane = self.query_one("#log", RichLog)
        pane.auto_scroll = not self._paused
        if not self._paused:
            self._redrawLog()
        self._updateTitles()

    def action_cycle_level(self) -> None:
        self._level_index = (self._level_index + 1) % len(LEVEL_CYCLE)
        self._redrawLog()
        self._updateTitles()

    def action_focus_search(self) -> None:
        search = self.query_one("#search", Input)
        search.add_class("visible")
        search.focus()

    def action_toggle_bus(self) -> None:
        self.query_one("#bus-pane", Vertical).toggle_class("hidden")

    def action_toggle_help(self) -> None:
        self.query_one("#help", Static).toggle_class("visible")

    def action_clear_search(self) -> None:
        search = self.query_one("#search", Input)
        search.value = ""
        search.remove_class("visible")
        self._search = ""
        self._redrawLog()
        self._updateTitles()
        self.query_one("#log", RichLog).focus()

    def action_dismiss_overlays(self) -> None:
        help_panel = self.query_one("#help", Static)
        if help_panel.has_class("visible"):
            help_panel.remove_class("visible")
            return
        self.action_clear_search()

    def action_copy(self) -> None:
        text = "\n".join(self._visibleLines())
        if not text:
            self.notify("nothing to copy", severity="warning")
            return
        self.notify(_copyToClipboard(self, text))

    def action_save(self) -> None:
        lines = self._visibleLines()
        if not lines:
            self.notify("nothing to save", severity="warning")
            return

        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        path = SAVE_DIR / f"viator-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
        path.write_text("\n".join(lines) + "\n")
        self.notify(f"saved {len(lines)} lines to {path}")

    def _visibleLines(self) -> list[str]:
        return [
            f"{r.clock} {r.level_name:<5} {r.node}  {r.message}"
            for r in self._records
            if self._shouldShow(r)
        ]

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._search = event.value.strip()
        self._redrawLog()
        self._updateTitles()
        self.query_one("#log", RichLog).focus()


def main() -> None:
    ViatorTui().run()


if __name__ == "__main__":
    main()
