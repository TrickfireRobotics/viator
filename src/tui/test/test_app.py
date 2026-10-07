"""
Drives the dashboard headlessly through Textual's pilot.

The UI is the one part of this repo that can be meaningfully tested off the rover: no CAN
bus, no cameras, no motors. These run inside the dev container, where ROS and textual are
both present, and skip anywhere they aren't.
"""

import asyncio
import functools
import time
from collections.abc import Callable, Coroutine
from typing import Any

import pytest

pytest.importorskip("textual", reason="textual is only installed in the dev container")
pytest.importorskip("rcl_interfaces", reason="needs a sourced ROS 2 environment")
pytest.importorskip("custom_interfaces", reason="needs the workspace to be built")

from rcl_interfaces.msg import Log
from textual.widgets import DataTable, Input, RichLog

from custom_interfaces.msg import NodeStatus
from tui.app import ViatorTui
from tui.bridge import LogRecord, StatusRecord

LEVEL_NAMES = {Log.DEBUG: "DEBUG", Log.INFO: "INFO", Log.WARN: "WARN", Log.ERROR: "ERROR"}


def asyncTest(fn: Callable[..., Coroutine[Any, Any, None]]) -> Callable[..., None]:
    """
    Runs an async test body in its own event loop.

    Deliberately hand-rolled instead of using pytest-asyncio: installing that pulls in a
    pytest new enough to drop the deprecated `path` hook argument, which breaks ROS's
    launch_testing plugin and takes `colcon test` down with it. functools.wraps keeps the
    signature intact so pytest still injects fixtures.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        asyncio.run(fn(*args, **kwargs))

    return wrapper


@pytest.fixture(autouse=True)
def _no_ros(monkeypatch):
    """
    Stops the app opening a real rclpy context; these tests feed records in directly.
    """
    import tui.app as app_mod

    monkeypatch.setattr(app_mod.RosBridge, "start", lambda self: None)
    monkeypatch.setattr(app_mod.RosBridge, "stop", lambda self: None)


def makeLog(level: int, node: str, message: str) -> LogRecord:
    return LogRecord(
        level=level,
        level_name=LEVEL_NAMES[level],
        node=node,
        message=message,
        seconds=int(time.time()),
        nanoseconds=0,
    )


@asyncTest
async def test_panes_mount():
    app = ViatorTui()
    async with app.run_test():
        assert len(app.query_one("#status", DataTable).columns) == 3
        assert app.query_one("#log", RichLog) is not None
        assert app.query_one("#search", Input) is not None


@asyncTest
async def test_status_rows_appear():
    app = ViatorTui()
    async with app.run_test() as pilot:
        app._applyStatus(StatusRecord("can_rmdx8", NodeStatus.DEGRADED, "6 motors, 284 drops"))
        app._applyStatus(StatusRecord("heartbeat", NodeStatus.OK, "connected"))
        await pilot.pause()
        assert app.query_one("#status", DataTable).row_count == 2


@asyncTest
async def test_default_filter_hides_debug():
    app = ViatorTui()
    async with app.run_test() as pilot:
        app._applyLog(makeLog(Log.INFO, "drivebase", "driving"))
        app._applyLog(makeLog(Log.DEBUG, "camera", "created publisher"))
        app._applyLog(makeLog(Log.ERROR, "can_rmdx8", "bus down"))
        await pilot.pause()

        shown = [r.level for r in app._records if app._shouldShow(r)]
        assert shown == [Log.INFO, Log.ERROR]


@asyncTest
async def test_pause_stops_autoscroll():
    app = ViatorTui()
    async with app.run_test() as pilot:
        await pilot.press("p")
        assert app._paused
        assert not app.query_one("#log", RichLog).auto_scroll

        await pilot.press("p")
        assert not app._paused


@asyncTest
async def test_level_key_cycles():
    app = ViatorTui()
    async with app.run_test() as pilot:
        start = app._level_index
        await pilot.press("f")
        assert app._level_index == (start + 1) % 4


@asyncTest
async def test_search_toggles_and_clears():
    app = ViatorTui()
    async with app.run_test() as pilot:
        await pilot.press("slash")
        await pilot.pause()
        assert app.query_one("#search", Input).has_class("visible")

        await pilot.press("escape")
        await pilot.pause()
        assert app._search == ""
        assert not app.query_one("#search", Input).has_class("visible")


@asyncTest
async def test_text_filter_narrows_log():
    app = ViatorTui()
    async with app.run_test() as pilot:
        app._applyLog(makeLog(Log.INFO, "drivebase", "driving forward"))
        app._applyLog(makeLog(Log.INFO, "camera", "publishing video0"))
        await pilot.pause()

        app._search = "video"
        app._redrawLog()

        shown = [r for r in app._records if app._shouldShow(r)]
        assert len(shown) == 1
        assert shown[0].node == "camera"


@asyncTest
async def test_save_writes_only_visible_lines(tmp_path, monkeypatch):
    import tui.app as app_mod

    monkeypatch.setattr(app_mod, "SAVE_DIR", tmp_path / "out")

    app = ViatorTui()
    async with app.run_test() as pilot:
        app._applyLog(makeLog(Log.INFO, "drivebase", "driving forward"))
        app._applyLog(makeLog(Log.DEBUG, "camera", "created publisher"))
        await pilot.pause()

        await pilot.press("s")
        await pilot.pause()

        files = list((tmp_path / "out").glob("*.log"))
        assert len(files) == 1

        body = files[0].read_text()
        assert "driving forward" in body
        assert "created publisher" not in body


@asyncTest
async def test_module_goes_stale_when_reports_stop():
    app = ViatorTui()
    async with app.run_test() as pilot:
        app._applyStatus(StatusRecord("arm", NodeStatus.OK, "mode disabled"))
        await pilot.pause()

        # backdate the last sighting past the stale threshold
        app._status_seen["arm"] = time.monotonic() - 10.0
        app._refreshStatus()
        await pilot.pause()

        cell = app.query_one("#status", DataTable).get_cell_at((0, 1))
        assert str(cell) == "stale"
