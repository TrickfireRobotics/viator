from rclpy.node import Node
from std_msgs.msg import Float32

from lib.color_codes import ColorCodes, colorStr
from lib.configs import MotorConfigs
from lib.interface.robot_interface import RobotInterface
from lib.node_runner import runNodes


class Drivebase(Node):
    SPEED = 6.28 * 1.5

    def __init__(self) -> None:
        super().__init__("drivebase")
        self.get_logger().info(colorStr("Launching drivebase node", ColorCodes.BLUE_OK))
        self.bot_interface = RobotInterface(self)

        self.left_subscription = self.create_subscription(
            Float32, "move_left_drivebase_side_message", self.moveLeftSide, 10
        )
        self.right_subscription = self.create_subscription(
            Float32, "move_right_drivebase_side_message", self.moveRightSide, 10
        )

    def moveLeftSide(self, msg: Float32) -> None:
        vel = msg.data * self.SPEED
        self.bot_interface.runMotorSpeed(MotorConfigs.FRONT_LEFT_DRIVE_MOTOR, vel)
        self.bot_interface.runMotorSpeed(MotorConfigs.MID_LEFT_DRIVE_MOTOR, vel)
        self.bot_interface.runMotorSpeed(MotorConfigs.REAR_LEFT_DRIVE_MOTOR, vel)

    def moveRightSide(self, msg: Float32) -> None:
        vel = msg.data * self.SPEED
        self.bot_interface.runMotorSpeed(MotorConfigs.FRONT_RIGHT_DRIVE_MOTOR, -vel)
        self.bot_interface.runMotorSpeed(MotorConfigs.MID_RIGHT_DRIVE_MOTOR, -vel)
        self.bot_interface.runMotorSpeed(MotorConfigs.REAR_RIGHT_DRIVE_MOTOR, -vel)

    def turnLeft(self, msg: Float32) -> None:
        self.moveLeftSide(msg)
        self.moveRightSide(-msg)

    def turnRight(self, msg: Float32) -> None:
        self.moveLeftSide(-msg)
        self.moveRightSide(msg)


def main(args: list[str] | None = None) -> None:
    runNodes(Drivebase, args=args)


if __name__ == "__main__":
    main()
