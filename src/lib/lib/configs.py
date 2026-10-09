"""
This module contains all the relevant configs for the rover, and any classes needed to hold the
configs.
"""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MotorTypes(Enum):
    """
    A class signifying motor types
    """

    RMDX8MOTOR = "rmdx8"
    MOTEUSMOTOR = "moteus"
    NONE = None


@dataclass(frozen=True, kw_only=True)
class MotorConfig:
    """
    A dataclass that contains config values relating to motors connected via the can bus.
    """

    can_id: int
    """
    The can id of the motor.
    """

    motor_type: MotorTypes = MotorTypes.NONE

    """
    The type of the motor.
    """

    config: dict[str, float | int] | None = None
    """
    The config of the motor.

    # Moteus

    See: https://github.com/mjbots/moteus/blob/main/docs/reference.md#c-configurable-values

    The `id.id` will be ignored.

    # RMD

    RMD settings can be completely controled by run settings
    """

    def getCanTopicName(self) -> str:
        """
        Gets the motor's topic name for data sourced from can.

        Returns the following format: `<type>motor_<can_id>_from_can`
        """
        return f"this_is_wrong_if_youre_seeing_this_{self.can_id}_from_can"

    def getInterfaceTopicName(self) -> str:
        """
        Gets the motor's topic name for data sourced from robot interface.

        Returns the following format: `<type>motor_<can_id>_from_interface`
        """
        return f"this_is_wrong_if_youre_seeing_this_{self.can_id}_from_interface"


@dataclass(frozen=True, kw_only=True)
class MoteusMotorConfig(MotorConfig):
    """
    A dataclass that contains config values relating to moteus motors connected via the can bus.
    """

    # Set the value of motor_type
    def __post_init__(self) -> None:
        # Can't use simple assignment since class is frozen
        object.__setattr__(self, "motor_type", MotorTypes.MOTEUSMOTOR)

    def getCanTopicName(self) -> str:
        return f"moteusmotor_{self.can_id}_from_can"

    def getInterfaceTopicName(self) -> str:
        return f"moteusmotor_{self.can_id}_from_interface"


@dataclass(frozen=True)
class RMDx8MotorConfig(MotorConfig):
    """
    A data class that contains config values relating to rmdx8 motors.
    """

    # Set the value of motor_type
    def __post_init__(self) -> None:
        object.__setattr__(self, "motor_type", MotorTypes.RMDX8MOTOR)

    def getCanTopicName(self) -> str:
        """
        Gets the motor's topic name for data sourced from can.
        Returns the following format: 'rmdx8motor_<can_id>_from_can'
        """
        return f"rmdx8motor_{self.can_id}_from_can"

    def getInterfaceTopicName(self) -> str:
        """
        Gets the motor's topic name for data sourced from robot interface.
        Returns the following format: 'rmdx8motor_<can_id>_from_interface'
        """
        return f"rmdx8motor_{self.can_id}_from_interface"


class MotorConfigs:
    """
    A constants class that contains motor constants.
    """

    # Drivebase
    REAR_RIGHT_DRIVE_MOTOR = RMDx8MotorConfig(can_id=25)
    MID_RIGHT_DRIVE_MOTOR = RMDx8MotorConfig(can_id=23)
    FRONT_RIGHT_DRIVE_MOTOR = RMDx8MotorConfig(can_id=21)

    REAR_LEFT_DRIVE_MOTOR = RMDx8MotorConfig(can_id=26)
    MID_LEFT_DRIVE_MOTOR = RMDx8MotorConfig(can_id=24)
    FRONT_LEFT_DRIVE_MOTOR = RMDx8MotorConfig(can_id=22)

    # Arm
    ARM_SHOULDER_MOTOR = MoteusMotorConfig(
        can_id=1,
        config={
            "servo.max_voltage": 56.0,
            "servopos.position_min": math.nan,
            "servopos.position_max": math.nan,
        },
    )
    ARM_ELBOW_MOTOR = MoteusMotorConfig(
        can_id=2,
        config={
            "motor_position.rotor_to_output_ratio": 0.01666,
            "servo.pwm_rate_hz": 60000,
            "servo.pid_position.kp": 10000.0,
            "servo.pid_position.ki": 0.0,
            "servo.pid_position.kd": 0.0,
            "servo.default_timeout_s": 1.0,
            "servo.max_current_A": 6.0,
            "servo.max_velocity": 0.1,
            "servopos.position_min": -0.5,
            "servopos.position_max": 0.0,
        },
    )
    ARM_LEFT_WRIST_MOTOR = MoteusMotorConfig(can_id=3, config={})
    ARM_RIGHT_WRIST_MOTOR = MoteusMotorConfig(can_id=4, config={})
    ARM_TURNTABLE_MOTOR = MoteusMotorConfig(
        can_id=5,
        config={
            "motor_position.rotor_to_output_ratio": 0.030581,
            "servo.pid_position.kp": 16.0,
            "servo.pid_position.ki": 0.0,
            "servo.pid_position.kd": 1.0,
            "servo.max_current_A": 10.0,
            "servo.max_velocity": 1.0,
            "servopos.position_min": math.nan,
            "servopos.position_max": math.nan,
        },
    )

    # Don't allow anyone to change this class's attributes
    def __setattr__(self, _: str, __: Any) -> Any:
        raise AttributeError("Trying to set attribute on a frozen instance")

    @classmethod
    def getAllMotors(cls) -> list[MotorConfig]:
        """
        Returns a list of every motor in this constants class.
        """
        # Simply return every attribute that doesn't start with an underscore and isn't this method
        return [
            value
            for key, value in cls.__dict__.items()
            if not key.startswith("_") and key != "getAllMotors"
        ]
