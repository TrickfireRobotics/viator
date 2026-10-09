# Write the code for the node, implement everything that you can until
# the other RMD task is finished. Make sure to mimic the behaviour of
# the current Moteus node, but not necessarily copy the code.


import math
from collections.abc import Callable
from threading import Lock
from typing import TypeGuard

import myactuator_rmd_py as rmd
import myactuator_rmd_py.can
import std_msgs.msg
from myactuator_rmd_py.actuator_state import Gains
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from rclpy.publisher import Publisher
from std_msgs.msg import String

from lib.configs import RMDx8MotorConfig
from lib.motor_state.rmd_motor_state import RMDX8MotorState, RMDX8RunSettings

from .can_health import CanHealth

DEGREE_TO_REV = 360


def _validOrZero(value: float | None) -> float:
    if not _checkValid(value):
        return 0.0
    return value


def _checkValid(value: float | None) -> TypeGuard[float]:
    if value is None or not math.isfinite(value):
        return False
    return True


class RMDx8Motor:
    """
    A wrapper class to interact with the RMDx8 actuator and the ROS nodes.
    """

    def __init__(
        self,
        config: RMDx8MotorConfig,
        driver: rmd.CanDriver,
        ros_node: Node,
        cb: Callable[[], None],
        driver_lock: Lock,
        health: CanHealth,
    ) -> None:
        self.config = config
        self._ros_node = ros_node
        self._health = health
        self.motor = rmd.ActuatorInterface(driver, config.can_id)
        self.mutex_lock = driver_lock
        self._callback_group = ReentrantCallbackGroup()
        self._publisher = self._createPublisher()
        self._poll_count = 0
        self._last_power: float = 0.0
        self._last_acceleration: float = 0.0
        # Hardware testing shows that this rate of polling is handled comfortably
        timer_period = 0.10
        self.timer = ros_node.create_timer(
            timer_period, callback=cb, callback_group=self._callback_group
        )

    # create a publisher
    def _createPublisher(self) -> Publisher:
        """
        The publisher to send data to.
        """
        topic_name = self.config.getCanTopicName()
        # Size of queue is 1. All additional ones are dropped
        publisher = self._ros_node.create_publisher(std_msgs.msg.String, topic_name, 1)
        self._ros_node.get_logger().debug(f"created publisher {topic_name}")
        return publisher

    def dataInCallback(self, msg: String) -> None:
        """
        Updates the RMDx8 motor state
        """
        run_settings = RMDX8RunSettings.fromJsonMsg(msg)

        try:
            with self.mutex_lock:
                # Stop if requested
                if run_settings.set_stop:
                    self.motor.stopMotor()
                    return

                # Else, set values
                if (
                    run_settings.speed_pi is not None
                    and run_settings.current_pi is not None
                    and run_settings.position_pi is not None
                ):
                    self.motor.setControllerGains(
                        Gains(
                            run_settings.current_pi,
                            run_settings.speed_pi,
                            run_settings.position_pi,
                        )
                    )
                elif (
                    run_settings.speed_pi is not None
                    or run_settings.current_pi is not None
                    or run_settings.position_pi is not None
                ):
                    raise ValueError("All 3 PiGains must all be defined or all be None")

                if _checkValid(run_settings.position):
                    # Position is 0.01 dps and velocity is dps
                    self.motor.sendPositionAbsoluteSetpoint(
                        run_settings.position * DEGREE_TO_REV * 100,
                        _validOrZero(run_settings.velocity) * DEGREE_TO_REV,
                    )
                if _checkValid(run_settings.velocity):
                    # Velocity is 0.01 dps
                    self.motor.sendVelocitySetpoint(run_settings.velocity * DEGREE_TO_REV * 100)

                if _checkValid(run_settings.current):
                    # Value is 0.01 A
                    self.motor.sendCurrentSetpoint(run_settings.current * 100)

                # Acceleration and type must both be set
                if _checkValid(run_settings.acceleration) != (
                    run_settings.acceleration_type is not None
                ):
                    raise ValueError(
                        "`acceleration` and `acceleration_type` must both be None or not None"
                    )
                if (
                    _checkValid(run_settings.acceleration)
                    and run_settings.acceleration_type is not None
                ):
                    # Acceleration is dps/s
                    self.motor.setAcceleration(
                        run_settings.acceleration * 360, run_settings.acceleration_type
                    )
        except myactuator_rmd_py.can.ControllerProblemError as e:
            self._health.recordFault(self.config.can_id, f"command: {e}")
        except myactuator_rmd_py.can.SocketException as e:
            self._health.recordError(self.config.can_id, f"command: {e}")
        except Exception as e:
            # The driver's exceptions aren't all under one base class, so a bus
            # glitch here must never be allowed to kill the whole node. Include
            # the exception's type since the driver doesn't give these a common
            # base class to catch, and knowing the type is what lets us add a
            # proper except clause for it later instead of it hiding here.
            self._health.recordError(self.config.can_id, f"command: {type(e).__name__}: {e}")

    def publishData(self) -> None:
        """
        Publishes data from the rmdx8 controller
        """
        self._health.recordPoll(self.config.can_id)
        try:
            with self.mutex_lock:
                self._poll_count += 1
                # Power and acceleration change slowly — only query every 5 ticks
                # to reduce CAN bus traffic from 4 transactions/poll to 2.
                if self._poll_count % 5 == 0:
                    self._last_power = self.motor.getMotorPower()
                    self._last_acceleration = self.motor.getAcceleration()
                state = RMDX8MotorState.fromRMDX8Data(
                    self.config.can_id,
                    self.motor.getMotorStatus1(),
                    self.motor.getMotorStatus2(),
                    self._last_power,
                    self._last_acceleration,
                )
            self._publisher.publish(state.toMsg())
        except myactuator_rmd_py.can.ControllerProblemError as e:
            self._health.recordFault(self.config.can_id, f"poll: {e}")
        except myactuator_rmd_py.can.SocketException as e:
            # EAGAIN means the response didn't arrive in time; the next tick retries
            if "Resource temporarily unavailable" in str(e):
                self._health.recordDrop(self.config.can_id)
            else:
                self._health.recordError(self.config.can_id, f"poll: {e}")
        except Exception as e:
            self._health.recordError(self.config.can_id, f"poll: {type(e).__name__}: {e}")

    def stopMotor(self) -> None:
        """
        Calls my_actuator_rmd stopMotor
        """
        try:
            with self.mutex_lock:
                self.motor.stopMotor()
        except Exception as e:
            self._ros_node.get_logger().error(
                f"Unexpected error in stopMotor for motor {self.config.can_id}: "
                f"{type(e).__name__}: {e}"
            )

    def shutdownMotor(self) -> None:
        """
        Calls my_actuator_rmd shutdownMotor
        """
        try:
            with self.mutex_lock:
                self.motor.shutdownMotor()
        except myactuator_rmd_py.can.SocketException as e:
            self._ros_node.get_logger().error(
                f"CAN error during shutdown for motor {self.config.can_id}: {e}"
            )
        except Exception as e:
            self._ros_node.get_logger().error(
                f"Unexpected error during shutdown for motor {self.config.can_id}: "
                f"{type(e).__name__}: {e}"
            )
