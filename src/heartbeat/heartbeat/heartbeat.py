import time

from rclpy.node import Node
from std_msgs.msg import Bool

from lib import configs
from lib.color_codes import ColorCodes, color_str
from lib.interface.robot_interface import RobotInterface
from lib.node_runner import run_nodes
from lib.status import StatusReporter

# Credit: Most of this code is credit to Anna. I (Hong) just
# add some finishing code and clean up the class.

# two missed heartbeats, so a single dropped message doesn't stop the rover
HEARTBEAT_TIMEOUT_SEC = 2.0


class Heartbeat(Node):
    """
    Watches mission control's heartbeat and stops every motor when it stops arriving.
    """

    def __init__(self) -> None:
        super().__init__("heartbeat_node")

        self._robot_interface = RobotInterface(self)

        # starts "lost" until the first heartbeat arrives
        self._connection_lost = True

        self._is_alive_subscriber = self.create_subscription(
            Bool, "/heartbeat", self.heartbeat_callback, 10
        )
        self._is_alive_publisher = self.create_publisher(Bool, "/hbr", 10)

        self._last_heartbeat_time = time.time()
        self._timer = self.create_timer(1.0, self.check_connection)

        self._status = StatusReporter(self, "heartbeat")
        self._status.ok("awaiting mission control")

    def heartbeat_callback(self, msg: Bool) -> None:
        self._last_heartbeat_time = time.time()

        # the data is always True, so this only checks the publisher is sane
        if msg.data:
            # INFO on the way into a connected state, DEBUG for the per-second tick
            if self._connection_lost:
                self.get_logger().info(color_str("Connection active", ColorCodes.GREEN_OK))
                self._status.ok("mission control connected")
                self._connection_lost = False
            else:
                self.get_logger().debug(color_str("Connection active", ColorCodes.GREEN_OK))

        # tell the client the heartbeat was received
        msg = Bool()
        msg.data = True
        self._is_alive_publisher.publish(msg)

    def check_connection(self) -> None:
        if time.time() - self._last_heartbeat_time > HEARTBEAT_TIMEOUT_SEC:
            # the motors are already stopped, nothing to do again
            if self._connection_lost:
                return

            self.get_logger().warning(color_str("Connection lost", ColorCodes.WARNING_YELLOW))
            self._status.degraded("mission control lost, motors stopped")
            self._connection_lost = True
            self._stop_all_motors()

    def _stop_all_motors(self) -> None:
        all_motors = configs.MotorConfigs.get_all_motors()
        for motor in all_motors:
            self._robot_interface.stop_motor(motor)

        # one line rather than one per motor: connection loss is routine in the field, and
        # 12 lines of it buried everything else that mattered at the same moment
        can_ids = " ".join(str(motor.can_id) for motor in all_motors)
        self.get_logger().warning(
            color_str(f"stopped all {len(all_motors)} motors ({can_ids})", ColorCodes.FAIL_RED)
        )


def main(args: list[str] | None = None) -> None:
    run_nodes(Heartbeat, args=args)


if __name__ == "__main__":
    main()
