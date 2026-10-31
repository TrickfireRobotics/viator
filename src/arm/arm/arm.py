from enum import IntEnum
from typing import Any

from rclpy.node import Node
from std_msgs.msg import Int32

from arm.individual_control_vel import IndividualControlVel
from custom_interfaces.srv import ArmMode
from lib.configs import MotorConfigs
from lib.interface.robot_interface import RobotInterface
from lib.node_runner import run_nodes
from lib.status import StatusReporter


class ArmModeEnum(IntEnum):
    DISABLED = 0
    INDIVIDUAL_MOTOR_CONTROL_VEL = 1
    INDIVIDUAL_MOTOR_CONTROL_POS = 2
    INVERSE_KINEMATICS = 3


class Arm(Node):
    def __init__(self) -> None:
        super().__init__("arm_node")

        self.change_arm_mode_sub = self.create_subscription(
            Int32, "update_arm_mode", self.update_arm_mode, 10
        )

        self.current_mode = ArmModeEnum.DISABLED

        self.mode_service = self.create_service(ArmMode, "get_arm_mode", self.mode_service_handler)

        self.bot_interface = RobotInterface(self)

        self.individual_control_vel = IndividualControlVel(self, self.bot_interface)

        self._status = StatusReporter(self, "arm")
        self._status.ok("mode disabled")

    def _mode_name(self) -> str:
        try:
            return ArmModeEnum(self.current_mode).name.lower()
        except ValueError:
            return f"unknown ({self.current_mode})"

    def mode_service_handler(self, _: Any, response: ArmMode.Response) -> ArmMode.Response:
        response.current_mode = int(self.current_mode)
        return response

    def update_arm_mode(self, msg: Int32) -> None:
        self.current_mode = msg.data
        self._status.ok(f"mode {self._mode_name()}")

        if self.current_mode == 0:
            self.bot_interface.disable_motor(MotorConfigs.ARM_TURNTABLE_MOTOR)
            self.bot_interface.disable_motor(MotorConfigs.ARM_SHOULDER_MOTOR)
            self.bot_interface.disable_motor(MotorConfigs.ARM_ELBOW_MOTOR)
            self.bot_interface.disable_motor(MotorConfigs.ARM_LEFT_WRIST_MOTOR)
            self.bot_interface.disable_motor(MotorConfigs.ARM_RIGHT_WRIST_MOTOR)

            self.individual_control_vel.can_send = False
        elif self.current_mode == 1:
            self.individual_control_vel.can_send = True
        elif self.current_mode == 2 or self.current_mode == 3:
            self.individual_control_vel.can_send = False


def main(args: list[str] | None = None) -> None:
    run_nodes(Arm, args=args)


if __name__ == "__main__":
    main()
