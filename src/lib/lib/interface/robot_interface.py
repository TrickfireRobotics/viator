"""
This module just contains the RobotInterface class. It provides utility functions to interact with
motors on the robot.
"""

import math

from rclpy.node import Node
from rclpy.publisher import Publisher
from std_msgs.msg import String

from lib.configs import MotorConfig, MotorConfigs
from lib.motor_state.can_motor_state import CanMotorRunSettings

REVS_TO_RADIANS = math.pi * 2
RADIANS_TO_REVS = 1 / REVS_TO_RADIANS


class RobotInterface:
    """
    A class that provides utility functions to interact with motors on the robot
    """

    def __init__(self, ros_node: Node) -> None:
        self._ros_node = ros_node
        self._publishers: dict[int, Publisher] = {}

        for motor_config in MotorConfigs.getAllMotors():
            if motor_config.can_id is None:
                continue
            self._publishers[motor_config.can_id] = self._ros_node.create_publisher(
                String, motor_config.getInterfaceTopicName(), 10
            )

    def runMotor(self, motor: MotorConfig, run_settings: CanMotorRunSettings) -> None:
        """
        Runs the specified motor with the specified settings.

        Parameters
        -------
        motor : MotorConfig
            The config of the motor to run.
        run_settings : CanMotorRunSettings
            The settings to run the motor with.
        """
        if motor.can_id is None:
            return
        self._publishers[motor.can_id].publish(run_settings.toMsg())

    def runMotorSpeed(self, motor: MotorConfig, target_radians_per_second: float) -> None:
        """
        Runs the specified motor with the specified target speed.

        Parameters
        -------
        motor : MotorConfig
            The config of the motor to run.
        target_radians_per_second: float
            The target speed in radians per second to run the motor.
        """
        self.runMotor(
            motor,
            CanMotorRunSettings(
                position=math.nan,
                velocity=target_radians_per_second * RADIANS_TO_REVS,
                set_stop=False,
            ),
        )

    def runMotorPosition(self, motor: MotorConfig, target_radians: float) -> None:
        """
        Runs the specified motor to reach the specified position.

        Parameters
        -------
        motor : MotorConfig
            The config of the motor to run.
        target_radians: float
            The target position in revolutions.
        """
        self.runMotor(
            motor, CanMotorRunSettings(position=target_radians * RADIANS_TO_REVS, set_stop=False)
        )

    def stopMotor(self, motor: MotorConfig) -> None:
        """
        Stops the specified motor. This will stop the motor in place, not make it go limp unlike
        `disableMotor()`.

        Parameters
        ------
        motor: MotorConfig
            The config of the motor to stop.
        """
        self.runMotor(motor, CanMotorRunSettings(position=math.nan, velocity=0, set_stop=False))

    def disableMotor(self, motor: MotorConfig) -> None:
        """
        Disables the specified motor. This essentially turns off the motor, stopping all output and
        making it go limp.

        Parameters
        -------
        motor : MotorConfig
            The config of the motor to disable.
        """
        self.runMotor(motor, CanMotorRunSettings(velocity=0, set_stop=True))
