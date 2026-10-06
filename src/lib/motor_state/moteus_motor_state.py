"""
This module contains objects representing the moteus motor state and settings for `set_position`.
"""

from dataclasses import dataclass

import moteus
from moteus.moteus import Result

from lib.motor_state.can_motor_state import CanMotorRunSettings, CANMotorState


@dataclass(frozen=True, kw_only=True)
class MoteusMotorState(CANMotorState["MoteusMotorState"]):
    """
    A dataclass representing the state of the moteus motor.
    """

    can_id: int = -1
    position: float | None = None
    """
    Current position of the motor in revolutions.
    """
    velocity: float | None = None
    """
    Current velocity of the motor in revolutions per second.
    """
    torque: float | None = None
    """
    Current torque of the motor in newton meters.
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
    q_current: float | None = None
    """
    Current q phase measured in amps.
    """
    d_current: float | None = None
    """
    Current d phase measured in amps.
    """

    @classmethod
    def fromMoteusData(cls, can_id: int, moteus_result: Result) -> "MoteusMotorState":
        """
        Creates a MoteusMotorState from a moteus result.
        """
        dict_ = {
            "can_id": can_id,
            "position": moteus_result.values[moteus.Register.POSITION],
            "velocity": moteus_result.values[moteus.Register.VELOCITY],
            "torque": moteus_result.values[moteus.Register.TORQUE],
            "temperature": moteus_result.values[moteus.Register.TEMPERATURE],
            "power": moteus_result.values[moteus.Register.POWER],
            "input_voltage": moteus_result.values[moteus.Register.VOLTAGE],
            "q_current": moteus_result.values[moteus.Register.Q_CURRENT],
            "d_current": moteus_result.values[moteus.Register.D_CURRENT],
        }

        return cls(**dict_)


@dataclass(frozen=True, kw_only=True)
class MoteusRunSettings(CanMotorRunSettings["MoteusRunSettings"]):
    """
    A dataclass representing the different settings while running a moteus motor.
    """

    position: float | None = None
    """
    Requested position of the motor in revolutions.
    """
    velocity: float | None = None
    """
    Requested velocity of the motor in revolutions per second.
    """
    feedforward_torque: float | None = None
    kp_scale: float | None = None
    kd_scale: float | None = None
    max_torque: float | None = None
    watchdog_timeout: float | None = None
    velocity_limit: float | None = None
    accel_limit: float | None = None
    fixed_voltage_override: float | None = None
    set_stop: bool = True
