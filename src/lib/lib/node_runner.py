"""
A single entry-point helper for every Viator node.

Each node used to hand-roll its own `main()`, and they disagreed about shutdown: some
caught `KeyboardInterrupt`, some didn't, and some called `rclpy.shutdown()` after rclpy's
own SIGINT handler had already torn the context down, which raises
`RCLError: rcl_shutdown already called` and makes every clean Ctrl-C look like a crash.
Routing all of them through here means shutdown behaves the same everywhere.
"""

import sys
from collections.abc import Callable, Sequence

import rclpy
import rclpy.logging
from rclpy.executors import (
    Executor,
    ExternalShutdownException,
    MultiThreadedExecutor,
    SingleThreadedExecutor,
)
from rclpy.node import Node

NodeFactory = Callable[[], Node | Sequence[Node]]
ExecutorFactory = Callable[[Sequence[Node]], Executor]


def multiThreaded(num_threads: int | None = None) -> ExecutorFactory:
    """
    An executor factory for nodes whose callbacks must run concurrently.

    Passing `None` lets rclpy size the pool from the CPU count.
    """

    def build(_: Sequence[Node]) -> Executor:
        return MultiThreadedExecutor(num_threads=num_threads)

    return build


def runNodes(
    factory: NodeFactory,
    *,
    args: list[str] | None = None,
    executor_factory: ExecutorFactory | None = None,
    on_shutdown: Callable[[Sequence[Node]], None] | None = None,
) -> None:
    """
    Initializes rclpy, spins the node(s) the factory returns, and shuts down cleanly.

    Parameters
    ------
    factory: NodeFactory
        Builds the node or nodes to spin. Called after `rclpy.init`. Exceptions raised
        here are deliberately left to propagate: a node that cannot start is a real
        failure and should exit non-zero so the launch system notices.
    args: list[str] | None
        Command line arguments forwarded to `rclpy.init`.
    executor_factory: ExecutorFactory | None
        Builds the executor to spin with. Defaults to single threaded.
    on_shutdown: Callable[[Sequence[Node]], None] | None
        Cleanup run before the nodes are destroyed, for things like stopping motors.
    """

    rclpy.init(args=args)

    nodes: list[Node] = []
    executor: Executor | None = None

    try:
        created = factory()
        nodes = [created] if isinstance(created, Node) else list(created)

        if not nodes:
            # spinning an executor with no nodes would just burn CPU; exiting lets the
            # launch system's respawn handle the retry instead
            rclpy.logging.get_logger("node_runner").error("no nodes to run, exiting")
            return

        executor = executor_factory(nodes) if executor_factory is not None else None
        if executor is None:
            executor = SingleThreadedExecutor()

        for node in nodes:
            executor.add_node(node)

        executor.spin()
    except KeyboardInterrupt:
        pass
    except ExternalShutdownException:
        pass
    finally:
        if on_shutdown is not None and nodes:
            try:
                on_shutdown(nodes)
            except Exception as e:
                # a failing cleanup hook must not replace the real reason we're exiting
                print(
                    f"error in shutdown hook: {type(e).__name__}: {e}",
                    file=sys.stderr,
                )

        if executor is not None:
            executor.shutdown()

        for node in nodes:
            node.destroy_node()

        # rclpy's SIGINT handler may already have shut the context down, in which case
        # shutting down again raises and turns a clean exit into a traceback
        if rclpy.ok():
            rclpy.shutdown()
