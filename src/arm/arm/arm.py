from enum import IntEnum
from typing import Any

from rclpy.node import Node
from std_msgs.msg import Int32

from custom_interfaces.srv import ArmMode
from lib.color_codes import ColorCodes, colorStr
from lib.configs import MotorConfigs
from lib.interface.robot_interface import RobotInterface
from lib.node_runner import runNodes
from lib.status import StatusReporter

from .individual_control_vel import IndividualControlVel


class ArmModeEnum(IntEnum):
    DISABLED = 0
    INDIVIDUAL_MOTOR_CONTROL_VEL = 1
    INDIVIDUAL_MOTOR_CONTROL_POS = 2
    INVERSE_KINEMATICS = 3


class Arm(Node):
    def __init__(self) -> None:
        super().__init__("arm_node")
        self.get_logger().info(colorStr("Launching arm_node", ColorCodes.BLUE_OK))

        self.change_arm_mode_sub = self.create_subscription(
            Int32, "update_arm_mode", self.updateArmMode, 10
        )

        self.current_mode = ArmModeEnum.DISABLED

        self.mode_service = self.create_service(ArmMode, "get_arm_mode", self.modeServiceHandler)

        self.bot_interface = RobotInterface(self)

        self.individual_control_vel = IndividualControlVel(self, self.bot_interface)

        self._status = StatusReporter(self, "arm")
        self._status.ok("mode disabled")

    def _modeName(self) -> str:
        """
        The current mode as a readable name, tolerating a value mission control shouldn't send.
        """
        try:
            return ArmModeEnum(self.current_mode).name.lower()
        except ValueError:
            return f"unknown ({self.current_mode})"

    def modeServiceHandler(self, _: Any, response: ArmMode.Response) -> ArmMode.Response:
        response.current_mode = int(self.current_mode)
        return response

    def updateArmMode(self, msg: Int32) -> None:
        self.current_mode = msg.data
        self._status.ok(f"mode {self._modeName()}")

        if self.current_mode == 0:
            self.bot_interface.disableMotor(MotorConfigs.ARM_TURNTABLE_MOTOR)
            self.bot_interface.disableMotor(MotorConfigs.ARM_SHOULDER_MOTOR)
            self.bot_interface.disableMotor(MotorConfigs.ARM_ELBOW_MOTOR)
            self.bot_interface.disableMotor(MotorConfigs.ARM_LEFT_WRIST_MOTOR)
            self.bot_interface.disableMotor(MotorConfigs.ARM_RIGHT_WRIST_MOTOR)

            self.individual_control_vel.can_send = False
        elif self.current_mode == 1:
            self.individual_control_vel.can_send = True
        elif self.current_mode == 2:
            self.individual_control_vel.can_send = False
        elif self.current_mode == 3:
            self.individual_control_vel.can_send = False


def main(args: list[str] | None = None) -> None:
    """
    The entry point of the node.
    """

    runNodes(Arm, args=args)


if __name__ == "__main__":
    main()
