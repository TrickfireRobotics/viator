import time
from collections.abc import Sequence

from rclpy.node import Node
from std_msgs.msg import Float32

from lib.color_codes import ColorCodes, colorStr
from lib.configs import MotorConfig, MotorConfigs
from lib.interface.robot_interface import RobotInterface
from lib.node_runner import runNodes
from lib.status import StatusReporter

# how long a drive command stays valid
# mission control republishes while a stick is held so a gap this long means the stream stopped
COMMAND_TIMEOUT_SEC = 0.5

WATCHDOG_PERIOD_SEC = 0.1

# mission control sends a normalised stick position, and anything outside it is an
# upstream bug the drivebase shouldn't amplify into a surprising wheel speed
MAX_INPUT = 1.0


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


class Drivebase(Node):
    SPEED = 6.28 * 1.5

    LEFT_MOTORS = (
        MotorConfigs.FRONT_LEFT_DRIVE_MOTOR,
        MotorConfigs.MID_LEFT_DRIVE_MOTOR,
        MotorConfigs.REAR_LEFT_DRIVE_MOTOR,
    )

    RIGHT_MOTORS = (
        MotorConfigs.FRONT_RIGHT_DRIVE_MOTOR,
        MotorConfigs.MID_RIGHT_DRIVE_MOTOR,
        MotorConfigs.REAR_RIGHT_DRIVE_MOTOR,
    )

    def __init__(self) -> None:
        super().__init__("drivebase")
        self.bot_interface = RobotInterface(self)

        self.left_subscription = self.create_subscription(
            Float32, "move_left_drivebase_side_message", self.moveLeftSide, 10
        )
        self.right_subscription = self.create_subscription(
            Float32, "move_right_drivebase_side_message", self.moveRightSide, 10
        )

        # starts stopped, so the watchdog stays quiet until the first real command
        self._stopped = True
        self._last_command_time = time.monotonic()
        self._watchdog = self.create_timer(WATCHDOG_PERIOD_SEC, self.checkCommandTimeout)

        self._status = StatusReporter(self, "drivebase")
        self._status.ok("awaiting commands")

    def moveLeftSide(self, msg: Float32) -> None:
        self._noteCommand()
        self._driveSide(self.LEFT_MOTORS, _clamp(msg.data, MAX_INPUT) * self.SPEED)

    def moveRightSide(self, msg: Float32) -> None:
        self._noteCommand()
        self._driveSide(self.RIGHT_MOTORS, -_clamp(msg.data, MAX_INPUT) * self.SPEED)

    def checkCommandTimeout(self) -> None:
        # zeroes the wheels when commands stop arriving. heartbeat_node covers mission
        # control disconnecting; this covers it staying connected with a stalled command
        # stream, and still works if heartbeat_node itself died. Motors hold their last
        # setpoint, so without this the rover keeps driving
        if self._stopped:
            return

        if time.monotonic() - self._last_command_time <= COMMAND_TIMEOUT_SEC:
            return

        self._stopped = True
        self.get_logger().debug(
            colorStr(
                f"no drive command for {COMMAND_TIMEOUT_SEC}s, zeroing drivebase",
                ColorCodes.WARNING_YELLOW,
            )
        )
        self._driveSide(self.LEFT_MOTORS, 0.0)
        self._driveSide(self.RIGHT_MOTORS, 0.0)
        self._status.ok("stopped, no commands")

    def _noteCommand(self) -> None:
        self._last_command_time = time.monotonic()
        if self._stopped:
            self._status.ok("driving")
        self._stopped = False

    def _driveSide(self, motors: Sequence[MotorConfig], velocity: float) -> None:
        for motor in motors:
            self.bot_interface.runMotorSpeed(motor, velocity)


def main(args: list[str] | None = None) -> None:
    runNodes(Drivebase, args=args)


if __name__ == "__main__":
    main()
