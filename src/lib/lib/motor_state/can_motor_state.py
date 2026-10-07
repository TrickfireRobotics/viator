"""
This module contains objects representing a can motor state and settings for setting position
setpoint.
"""

from dataclasses import dataclass
from typing import TypeVar

from lib.json_msg import JsonMsg

T = TypeVar("T")


@dataclass(frozen=True, kw_only=True)
class CANMotorState(JsonMsg[T]):
    """
    A dataclass representing the state of the motor.
    """

    can_id: int | None = None
    position: float | None = None
    """
    Current position of the motor in revolutions.
    """
    velocity: float | None = None
    """
    Current velocity of the motor in revolutions per second.
    """
    current: float | None = None
    """
    Current of the motor in Amperes.
    """
    temperature: float | None = None
    """
    Current temperature of the controller in celcius.
    """
    power: float | None = None
    """
    Current power draw of the controller in watts.
    """
    input_voltage: float | None = None
    """
    Current voltage of the controller in volts.
    """


@dataclass(frozen=True, kw_only=True)
class CanMotorRunSettings(JsonMsg[T]):
    """
    A dataclass representing the different settings while running a motor.
    """

    position: float | None = None
    """
    Requested position of the motor in revolutions.
    """
    velocity: float | None = None
    """
    Requested velocity of the motor in revolutions per second.
    """
    velocity_limit: float | None = None
    set_stop: bool = True
