"""
The Viator terminal dashboard: module status on top, live log and CAN traffic underneath.

Reads `/viator/node_status` for the status pane, follows the launch-output file for the
log pane, and follows `candump` for the bus pane. The file is used alongside `/rosout` so
startup output, Python tracebacks, and native-library warnings are present even when the
dashboard opens after the graph starts.

Everything here draws on a transparent background on purpose: the dashboard sits in the
operator's terminal, so it borrows their colours rather than painting over them.
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
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, RichLog, Static

from custom_interfaces.msg import NodeStatus
from lib.status import STATE_NAMES

from .bridge import CAN_IFACE, CanFrame, LogRecord, RosBridge, StatusRecord

# Levels the `f` key cycles through, as a minimum threshold.
LEVEL_CYCLE = [Log.DEBUG, Log.INFO, Log.WARN, Log.ERROR]

LEVEL_LABELS = {
    Log.DEBUG: "debug+",
    Log.INFO: "info+",
    Log.WARN: "warn+",
    Log.ERROR: "error",
}

# The level marker is a gutter rather than a word: `INFO` down the left of four hundred
# lines is four hundred repetitions of the least interesting thing on each one. A bar
# that only changes colour when something is wrong reads at a glance and costs no width.
LEVEL_GUTTER = {
    Log.DEBUG: ("┊", "dim"),
    Log.INFO: ("│", "dim"),
    Log.WARN: ("┃", "yellow"),
    Log.ERROR: ("┃", "bold red"),
    Log.FATAL: ("┃", "bold white on red"),
}

MESSAGE_STYLES = {
    Log.DEBUG: "dim",
    Log.WARN: "yellow",
    Log.ERROR: "red",
    Log.FATAL: "bold red",
}

STATE_STYLES = {
    NodeStatus.STARTING: "cyan",
    NodeStatus.OK: "green",
    NodeStatus.DEGRADED: "yellow",
    NodeStatus.FAILED: "bold red",
}

STALE_STYLE = "bold red"

# One colour per CAN id, picked from the id itself so a given motor keeps its colour for
# the whole run. Six motors all in one colour is a wall of hex; six colours is a pattern
# you can see break when one of them stops answering.
BUS_ID_STYLES = ("cyan", "magenta", "green", "blue", "bright_cyan", "bright_magenta")

# Width of the node column in the log. Long enough for every module name the rover has.
NODE_WIDTH = 15

# Everything to the left of a log message: `HH:MM:SS`, the level gutter, the module, and
# a space before the message starts.
PREFIX_WIDTH = 8 + 3 + NODE_WIDTH + 1

# Enough history to scroll back through a run without growing without bound.
BUFFER_SIZE = 5000

# The bus pane is a window on live traffic, not a record of it, so it keeps far less.
BUS_BUFFER_SIZE = 500

# Frames arrive faster than a terminal can usefully redraw, so they are batched onto the
# UI thread on a timer instead of one call per frame.
BUS_DRAIN_PERIOD_SEC = 0.1
BUS_DRAIN_LIMIT = 24

# Matches the supervisor: a module republishes every second, so three misses means gone.
STALE_AFTER_SEC = 3.0

SAVE_DIR = Path.home() / ".ros" / "viator-tui"

# Where the launch's own stdout went, if whatever started us said so. Set by scripts/run.sh.
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


def shortNodeName(name: str) -> str:
    """
    The module name out of a ROS node name.

    `/can_rmdx8_node` and `can_rmdx8` are the same module to anyone reading the log, and
    the column is narrow, so spend its width on the part that differs.
    """
    short = name.lstrip("/").rsplit("/", 1)[-1]
    if short.endswith("_node"):
        short = short[: -len("_node")]
    if len(short) > NODE_WIDTH:
        return short[: NODE_WIDTH - 1] + "…"
    return short


class ViatorTui(App[None]):
    """
    The dashboard application.
    """

    TITLE = "viator"

    # The one theme whose colours are the terminal's own. Everything else in Textual
    # paints an opaque surface underneath itself, so this is what makes the dashboard sit
    # in the operator's terminal instead of on top of it, and it means the dashboard
    # matches whatever palette they already run.
    THEME = "ansi-dark"

    CSS = """
    Screen {
        layout: vertical;
        layers: base overlay;
        background: transparent;
    }

    /* The dashboard is a frame around the terminal's own background, not a replacement
       for it, so nothing below here paints a surface of its own. */
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
        /* A live feed, not a document: there is nothing to scroll back to, so the bar
           would only ever be decoration sitting in the narrowest pane. */
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

    /* The one thing that does get a background: it sits on top of the log and has to be
       readable against whatever is under it. */
    #help {
        layer: overlay;
        display: none;
        width: auto;
        max-width: 80;
        height: auto;
        max-height: 100%;
        border: round $border;
        border-title-align: left;
        /* The one opaque thing in the whole dashboard: it covers the log while it's
           open, so it has to hide what's underneath rather than blend into it. */
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

        self._bus_pending: deque[CanFrame] = deque(maxlen=BUS_BUFFER_SIZE)
        self._bus_ids: set[str] = set()
        self._bus_count = 0
        self._bus_rate = 0
        self._bus_state = "waiting"

        self._paused = False
        self._level_index = LEVEL_CYCLE.index(Log.INFO)
        self._search = ""

        self._bridge = RosBridge(
            on_status=self._handleStatus,
            on_log=self._handleLog,
            launch_log=Path(LAUNCH_LOG_HINT),
            on_frame=self._bus_pending.append,
            on_bus_state=self._handleBusState,
        )

    # ***************
    # Composition and lifecycle
    # ***************
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
                yield RichLog(id="bus", wrap=False, highlight=False, auto_scroll=True, min_width=0)

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
        self.set_interval(BUS_DRAIN_PERIOD_SEC, self._drainBus)
        self._updateTitles()

    def on_unmount(self) -> None:
        self._bridge.stop()

    # ***************
    # Callbacks from the background threads
    # ***************
    def _handleStatus(self, record: StatusRecord) -> None:
        """
        Called off the UI thread, so hand the work back to it.
        """
        self.call_from_thread(self._applyStatus, record)

    def _handleLog(self, record: LogRecord) -> None:
        self.call_from_thread(self._applyLog, record)

    def _handleBusState(self, state: str) -> None:
        self._bus_state = state

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

    def _drainBus(self) -> None:
        """
        Moves a batch of frames into the bus pane and recomputes the rate.

        The bus runs at thousands of frames a second when the drivebase is moving. Drawing
        every one of them would spend the whole frame budget on text nobody can read at
        that speed, so this takes a slice and reports the rate for the rest.
        """
        pane = self.query_one("#bus", RichLog)
        drained = 0
        while self._bus_pending and drained < BUS_DRAIN_LIMIT:
            frame = self._bus_pending.popleft()
            self._bus_ids.add(frame.can_id)
            self._bus_count += 1
            drained += 1
            if not self._paused:
                pane.write(self._renderFrame(frame))

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

    def _renderRecord(self, record: LogRecord) -> Table:
        """
        One log line: timestamp, level gutter, module, message.

        A two column grid rather than one string, so a message too long for the pane
        wraps under itself instead of starting again at the left margin and breaking up
        the column of timestamps that makes the log scannable.
        """
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
        """
        One CAN frame: id, length, payload.
        """
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
                label, style = "stale", STALE_STYLE
            else:
                label = STATE_NAMES.get(record.state, "unknown")
                style = STATE_STYLES.get(record.state, "white")

            module = Text.assemble(("● ", style), name)
            table.add_row(module, Text(label, style=style), Text(record.detail, style="dim"))

        self._updateTitles()

    def _refreshBusRate(self) -> None:
        """
        Turns a second's worth of frames into the rate shown on the bus pane.
        """
        self._bus_rate = self._bus_count
        self._bus_count = 0
        self._updateTitles()

    def _statusSummary(self) -> Text:
        """
        The modules border subtitle: how many are fine and how many aren't.
        """
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
        """
        Keeps the pane borders showing what each pane is currently doing.
        """
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

    def action_toggle_bus(self) -> None:
        """
        Hides the bus pane, for when the log is the thing you're reading.
        """
        self.query_one("#bus-pane", Vertical).toggle_class("hidden")

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
        text = "\n".join(self._visibleLines())
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
        lines = self._visibleLines()
        if not lines:
            self.notify("nothing to save", severity="warning")
            return

        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        path = SAVE_DIR / f"viator-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
        path.write_text("\n".join(lines) + "\n")
        self.notify(f"saved {len(lines)} lines to {path}")

    def _visibleLines(self) -> list[str]:
        """
        The log as plain text, for the clipboard and for saving.
        """
        return [
            f"{r.clock} {r.level_name:<5} {r.node}  {r.message}"
            for r in self._records
            if self._shouldShow(r)
        ]

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
