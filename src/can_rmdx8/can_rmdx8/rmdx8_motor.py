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

from can_rmdx8.can_health import CanHealth
from lib.configs import RMDx8MotorConfig
from lib.motor_state.rmd_motor_state import RMDX8MotorState, RMDX8RunSettings

DEGREE_TO_REV = 360


def _valid_or_zero(value: float | None) -> float:
    if not _check_valid(value):
        return 0.0
    return value


def _check_valid(value: float | None) -> TypeGuard[float]:
    return value is not None and math.isfinite(value)


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
        self._publisher = self._create_publisher()
        self._poll_count = 0
        self._last_power: float = 0.0
        self._last_acceleration: float = 0.0
        # Hardware testing shows that this rate of polling is handled comfortably
        timer_period = 0.10
        self.timer = ros_node.create_timer(
            timer_period, callback=cb, callback_group=self._callback_group
        )

    # create a publisher
    def _create_publisher(self) -> Publisher:
        """
        The publisher to send data to.
        """
        topic_name = self.config.get_can_topic_name()
        # Size of queue is 1. All additional ones are dropped
        publisher = self._ros_node.create_publisher(std_msgs.msg.String, topic_name, 1)
        self._ros_node.get_logger().debug(f"created publisher {topic_name}")
        return publisher

    def data_in_callback(self, msg: String) -> None:
        """
        Updates the RMDx8 motor state
        """
        run_settings = RMDX8RunSettings.from_json_msg(msg)

        try:
            with self.mutex_lock:
                # Stop if requested
                if run_settings.set_stop:
                    self.motor.stop_motor()
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

                if _check_valid(run_settings.position):
                    # Position is 0.01 dps and velocity is dps
                    self.motor.sendPositionAbsoluteSetpoint(
                        run_settings.position * DEGREE_TO_REV * 100,
                        _valid_or_zero(run_settings.velocity) * DEGREE_TO_REV,
                    )
                if _check_valid(run_settings.velocity):
                    # Velocity is 0.01 dps
                    self.motor.sendVelocitySetpoint(run_settings.velocity * DEGREE_TO_REV * 100)

                if _check_valid(run_settings.current):
                    # Value is 0.01 A
                    self.motor.sendCurrentSetpoint(run_settings.current * 100)

                # Acceleration and type must both be set
                if _check_valid(run_settings.acceleration) != (
                    run_settings.acceleration_type is not None
                ):
                    raise ValueError(
                        "`acceleration` and `acceleration_type` must both be None or not None"
                    )
                if (
                    _check_valid(run_settings.acceleration)
                    and run_settings.acceleration_type is not None
                ):
                    # Acceleration is dps/s
                    self.motor.setAcceleration(
                        run_settings.acceleration * 360, run_settings.acceleration_type
                    )
        except myactuator_rmd_py.can.ControllerProblemError as e:
            self._health.record_fault(self.config.can_id, f"command: {e}")
        except myactuator_rmd_py.can.SocketException as e:
            self._health.record_error(self.config.can_id, f"command: {e}")
        except Exception as e:
            # the driver's exceptions have no common base class, so a bus glitch would
            # otherwise kill the node. The type is logged so it can get its own clause.
            self._health.record_error(self.config.can_id, f"command: {type(e).__name__}: {e}")

    def publish_data(self) -> None:
        """
        Publishes data from the rmdx8 controller
        """
        self._health.record_poll(self.config.can_id)
        try:
            with self.mutex_lock:
                self._poll_count += 1
                # power and acceleration change slowly, so querying every 5th tick takes
                # the bus traffic from 4 transactions per poll to 2
                if self._poll_count % 5 == 0:
                    self._last_power = self.motor.getMotorPower()
                    self._last_acceleration = self.motor.getAcceleration()
                state = RMDX8MotorState.from_rmdx8_data(
                    self.config.can_id,
                    self.motor.getMotorStatus1(),
                    self.motor.getMotorStatus2(),
                    self._last_power,
                    self._last_acceleration,
                )
            self._publisher.publish(state.to_msg())
        except myactuator_rmd_py.can.ControllerProblemError as e:
            self._health.record_fault(self.config.can_id, f"poll: {e}")
        except myactuator_rmd_py.can.SocketException as e:
            # EAGAIN means the response didn't arrive in time; the next tick retries
            if "Resource temporarily unavailable" in str(e):
                self._health.record_drop(self.config.can_id)
            else:
                self._health.record_error(self.config.can_id, f"poll: {e}")
        except Exception as e:
            self._health.record_error(self.config.can_id, f"poll: {type(e).__name__}: {e}")

    def stop_motor(self) -> None:
        """
        Calls my_actuator_rmd stop_motor
        """
        try:
            with self.mutex_lock:
                self.motor.stop_motor()
        except Exception as e:
            self._ros_node.get_logger().error(
                f"Unexpected error in stop_motor for motor {self.config.can_id}: "
                f"{type(e).__name__}: {e}"
            )

    def shutdown_motor(self) -> None:
        """
        Calls my_actuator_rmd shutdown_motor
        """
        try:
            with self.mutex_lock:
                self.motor.shutdown_motor()
        except myactuator_rmd_py.can.SocketException as e:
            self._ros_node.get_logger().error(
                f"CAN error during shutdown for motor {self.config.can_id}: {e}"
            )
        except Exception as e:
            self._ros_node.get_logger().error(
                f"Unexpected error during shutdown for motor {self.config.can_id}: "
                f"{type(e).__name__}: {e}"
            )
