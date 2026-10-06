import sys
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Float32
from usb.core import Device
from usb.core import find as finddev

from lib.color_codes import ColorCodes, colorStr
from lib.configs import MoteusMotorConfig, MotorConfigs

from . import moteus_thread_manager


class RosMotuesBridge(Node):
    """
    This is the node that connects the Moteus Motor Controllers
    with the rest of the ROS codebase. You can easily add new
    motors using the addMotor() function from the self.threadManager.

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
        self.get_logger().info(colorStr("Launching can_moteus node", ColorCodes.BLUE_OK))

        self.thread_manager: moteus_thread_manager.MoteusThreadManager | None = None

        # Find the CANFD-USB. Retry because a just-launched (or just-reset) adapter
        # can take a moment to appear on the bus.
        dev = self._findCanFdUsb()
        if dev is None:
            self.get_logger().error(
                colorStr(
                    "Failed to find CANFD-USB usb device. Is it plugged in, or is another "
                    "process (e.g. ModemManager/brltty on the host) claiming it?",
                    ColorCodes.FAIL_RED,
                )
            )
            self._logVisibleUsbDevices()
            return

        # Reset the CANFD-USB so it starts from a clean state, then wait for it to
        # re-enumerate before the moteus library tries to open it. Without this wait
        # the moteus transport can grab the device mid-reset and fail to find it.
        dev.reset()
        if self._findCanFdUsb() is None:
            self.get_logger().error(
                colorStr("CANFD-USB did not re-appear after reset.", ColorCodes.FAIL_RED)
            )
            return

        self.reconnect_to_moteus_sub = self.create_subscription(
            Float32, "reconnectMoteusControllers", self.reconnect, 1
        )

        self.createMoteusMotors()

    def _findCanFdUsb(self) -> Device | None:
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

    def _logVisibleUsbDevices(self) -> None:
        """
        Logs every USB device currently visible to the container. Helps distinguish
        "not forwarded to the container" (list is empty/short) from "present under a
        different id, or intermittently grabbed by something else" (device is/isn't
        in the list depending on when this runs).
        """
        devices = list(finddev(find_all=True))
        if not devices:
            self.get_logger().warn(
                colorStr(
                    "No USB devices are visible at all. The container may not have USB "
                    "forwarded (check --privileged / device passthrough).",
                    ColorCodes.WARNING_YELLOW,
                )
            )
            return

        device_list = ", ".join(f"{d.idVendor:04x}:{d.idProduct:04x}" for d in devices)
        self.get_logger().warn(
            colorStr(f"USB devices visible now: {device_list}", ColorCodes.WARNING_YELLOW)
        )

    def reconnect(self, _: Float32) -> None:
        """
        Gracefully shuts down the threadManager and creates a new instance of
        the threadManager object.

        """
        self.get_logger().info("Reconnecting")
        if self.thread_manager is not None:
            self.thread_manager.reconnectMotors()

    def createMoteusMotors(self) -> None:
        """
        Creates the threadManager and adds all the moteus motors
        """

        self.thread_manager = moteus_thread_manager.MoteusThreadManager(self)

        for config in MotorConfigs.getAllMotors():
            if not isinstance(config, MoteusMotorConfig):
                continue
            self.thread_manager.addMotor(config)

        self.thread_manager.start()


def main(args: list[str] | None = None) -> None:
    """
    The entry point of the node.
    """

    rclpy.init(args=args)
    try:
        node = RosMotuesBridge()
        rclpy.spin(node)

    except KeyboardInterrupt:
        pass
    except ExternalShutdownException:
        # This is done when we ctrl-c the progam to shut it down
        node.get_logger().info(colorStr("Shutting down can_moteus", ColorCodes.BLUE_OK))
        if node.thread_manager is not None:
            node.thread_manager.terminateAllThreads()
        node.destroy_node()
        sys.exit(0)


if __name__ == "__main__":
    main()
