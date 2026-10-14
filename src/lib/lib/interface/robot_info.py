"""
This module just contains the RobotInfo class. It provides utility functions to access the state of
motor on the robot.
"""

from typing import Callable

from rclpy.node import Node
from rclpy.subscription import Subscription
from std_msgs.msg import String

from lib.configs import MotorConfig, MotorConfigs, MotorTypes
from lib.motor_state.can_motor_state import CANMotorState
from lib.motor_state.moteus_motor_state import MoteusMotorState
from lib.motor_state.rmd_motor_state import RMDX8MotorState


class RobotInfo:  # pylint: disable=too-few-public-methods
    """
    A class that provides utility functions to access the state of motors within the robot.
    """

    def __init__(self, ros_node: Node):
        self._ros_node = ros_node
        self.sub_list: list[Subscription] = []  # empty array
        self.can_id_to_json: dict[int, CANMotorState] = {}

        for motor_config in MotorConfigs.getAllMotors():
            if motor_config.can_id is None or motor_config.motor_type == MotorTypes.NONE:
                continue
            self._ros_node.create_subscription(
                String,
                motor_config.getCanTopicName(),
                self._createSubCallback(motor_config.motor_type),
                10,
            )
            self.can_id_to_json[motor_config.can_id] = CANMotorState()

    def _createSubCallback(self, motor_type: MotorTypes) -> Callable[[String], None]:
        # this is bad code design, but it's so small scale who cares
        state_cls: type
        if motor_type == MotorTypes.MOTEUSMOTOR:
            state_cls = MoteusMotorState
        elif motor_type == MotorTypes.RMDX8MOTOR:
            state_cls = RMDX8MotorState
        else:
            return lambda _: None

        def _subCallback(msg: String) -> None:
            state = state_cls.fromJsonMsg(msg)
            if state.can_id is None:
                return
            self.can_id_to_json[state.can_id] = state

        return _subCallback

    def getMotorState(self, motor: MotorConfig) -> CANMotorState:
        """
        Gets the state of the motor with the given can_id.

        Parameters
        ------
        can_id: int
            The can id of the motor to get the state of.
        """
        if motor.can_id is None:
            self._ros_node.get_logger().error(
                "Invalid motor, motor config passed has can id of type None"
            )
            return CANMotorState()
        return self.can_id_to_json[motor.can_id]
