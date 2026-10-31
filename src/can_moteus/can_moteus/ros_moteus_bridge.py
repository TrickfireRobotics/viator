import time
from collections.abc import Sequence

from rclpy.node import Node
from std_msgs.msg import Float32
from usb.core import Device
from usb.core import find as finddev

from can_moteus import moteus_thread_manager
from lib.color_codes import ColorCodes, color_str
from lib.configs import MoteusMotorConfig, MotorConfigs
from lib.node_runner import run_nodes


class RosMotuesBridge(Node):
    """
    This is the node that connects the Moteus Motor Controllers
    with the rest of the ROS codebase. You can easily add new
    motors using the add_motor() function from the self.threadManager.

    You can attempt to reconnect to the Moteus Controllers during runtime.
    The CANFD-USB is reset every time the code is execute from the ./launch.sh
    """

    # USB identifiers for the CANFD-USB (fdcanusb) adapter used by the moteus motors.
    # Run "lsusb" with the CANFD-USB connected to find the idVendor/idProduct.
    _CANFD_USB_VENDOR_ID = 0x0483
    _CANFD_USB_PRODUCT_ID = 0x5740

    # The adapter is reset on every launch, which briefly drops it off the USB bus,
    # and it can be slow to (re)enumerate. Retry the lookup instead of giving up on
    # the first miss (e.g. a relaunch racing the previous run's reset).
    _FIND_ATTEMPTS = 20
    _FIND_RETRY_DELAY_SEC = 0.5

    def __init__(self) -> None:
        super().__init__("can_moteus_node")

        self.thread_manager: moteus_thread_manager.MoteusThreadManager | None = None

        # Find the CANFD-USB. Retry because a just-launched (or just-reset) adapter
        # can take a moment to appear on the bus.
        dev = self._find_can_fd_usb()
        if dev is None:
            self.get_logger().error(
                color_str(
                    "Failed to find CANFD-USB usb device. Is it plugged in, or is another "
                    "process (e.g. ModemManager/brltty on the host) claiming it?",
                    ColorCodes.FAIL_RED,
                )
            )
            self._log_visible_usb_devices()
            return

        # Reset the CANFD-USB so it starts from a clean state, then wait for it to
        # re-enumerate before the moteus library tries to open it. Without this wait
        # the moteus transport can grab the device mid-reset and fail to find it.
        dev.reset()
        if self._find_can_fd_usb() is None:
            self.get_logger().error(
                color_str("CANFD-USB did not re-appear after reset.", ColorCodes.FAIL_RED)
            )
            return

        self.reconnect_to_moteus_sub = self.create_subscription(
            Float32, "reconnectMoteusControllers", self.reconnect, 1
        )

        self.create_moteus_motors()

    def _find_can_fd_usb(self) -> Device | None:
        """
        Look for the CANFD-USB adapter on the USB bus, retrying for a short while so
        a transient absence (e.g. it was just reset by a previous launch) doesn't
        cause us to give up.
        """
        for attempt in range(self._FIND_ATTEMPTS):
            dev = finddev(idVendor=self._CANFD_USB_VENDOR_ID, idProduct=self._CANFD_USB_PRODUCT_ID)
            if dev is not None:
                return dev
            if attempt < self._FIND_ATTEMPTS - 1:
                time.sleep(self._FIND_RETRY_DELAY_SEC)
        return None

    def _log_visible_usb_devices(self) -> None:
        """
        Logs every USB device currently visible to the container. Helps distinguish
        "not forwarded to the container" (list is empty/short) from "present under a
        different id, or intermittently grabbed by something else" (device is/isn't
        in the list depending on when this runs).
        """
        devices = list(finddev(find_all=True))
        if not devices:
            self.get_logger().warn(
                color_str(
                    "No USB devices are visible at all. The container may not have USB "
                    "forwarded (check --privileged / device passthrough).",
                    ColorCodes.WARNING_YELLOW,
                )
            )
            return

        device_list = ", ".join(f"{d.idVendor:04x}:{d.idProduct:04x}" for d in devices)
        self.get_logger().warn(
            color_str(f"USB devices visible now: {device_list}", ColorCodes.WARNING_YELLOW)
        )

    def reconnect(self, _: Float32) -> None:
        """
        Gracefully shuts down the threadManager and creates a new instance of
        the threadManager object.

        """
        self.get_logger().info("Reconnecting")
        if self.thread_manager is not None:
            self.thread_manager.reconnect_motors()

    def create_moteus_motors(self) -> None:
        """
        Creates the threadManager and adds all the moteus motors
        """

        self.thread_manager = moteus_thread_manager.MoteusThreadManager(self)

        for config in MotorConfigs.get_all_motors():
            if not isinstance(config, MoteusMotorConfig):
                continue
            self.thread_manager.add_motor(config)

        self.thread_manager.start()


def _stop_threads(nodes: Sequence[Node]) -> None:
    for node in nodes:
        if isinstance(node, RosMotuesBridge) and node.thread_manager is not None:
            node.thread_manager.terminate_all_threads()


def main(args: list[str] | None = None) -> None:
    """
    The entry point of the node.
    """

    run_nodes(RosMotuesBridge, args=args, on_shutdown=_stop_threads)


if __name__ == "__main__":
    main()
