import os
import sys
from collections import deque
from collections.abc import Sequence
from threading import Lock

import myactuator_rmd_py as rmd
import std_msgs.msg
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import Executor, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.subscription import Subscription
from std_msgs.msg import String

from can_rmdx8.can_health import CanHealth
from can_rmdx8.rmdx8_motor import RMDx8Motor
from lib.configs import MotorConfigs, RMDx8MotorConfig
from lib.node_runner import run_nodes
from lib.status import StatusReporter


class RMDx8MotorManager(Node):
    """
    Class to manage the control and storage of RMDx8 motors in the ROS system.
    """

    _UPDATE_STATE = "UPDATE_STATE"

    # the scripts export CAN_IFACE into the container, so setting it there moves the whole
    # stack to another bus
    _DEFAULT_CAN_IFACE = "can0"

    def __init__(self) -> None:
        super().__init__("can_rmdx8_node")
        self._id_to_rmdx8_motor: dict[int, RMDx8Motor] = {}
        self._can_iface = os.environ.get("CAN_IFACE") or self._DEFAULT_CAN_IFACE
        self.driver = rmd.CanDriver(self._can_iface)
        self._driver_lock = Lock()
        self._req_buffer: deque[tuple[int, String]] = deque(maxlen=1000)
        self._buffer_lock = Lock()
        self.health = CanHealth(self)
        self.create_rmdx8_motors()
        # Hardware testing
        self.create_timer(0.005, self._handle_requests)

        self._status = StatusReporter(self, "can_rmdx8")
        summary = f"{self.motor_count()} motors on {self._can_iface}"
        self._status.ok(summary)
        self.health.set_status_reporter(self._status, summary)
        self.get_logger().info(f"can_rmdx8 ready, {summary}")

    def _create_subscriber(self, config: RMDx8MotorConfig) -> Subscription:
        can_id = config.can_id
        return self.create_subscription(
            std_msgs.msg.String,
            config.get_interface_topic_name(),
            # We pass the create_request lambda with the
            # capture clause as the motor_id's can id
            # so we know who is making the requests
            lambda msg: self._create_request(can_id, msg),
            1,
            callback_group=ReentrantCallbackGroup(),
        )

    def shutdown_motors(self) -> None:
        """
        Shutdown all motors
        """
        for motor in self._id_to_rmdx8_motor.values():
            motor.shutdown_motor()

    def add_motor(self, config: RMDx8MotorConfig) -> None:
        """
        Adds new rmdx8 motor to the motor dictionary
        """

        motor = RMDx8Motor(
            config,
            self.driver,
            self,
            lambda: self._create_request(config.can_id, String(data=self._UPDATE_STATE)),
            self._driver_lock,
            self.health,
        )
        self._id_to_rmdx8_motor[config.can_id] = motor
        self._create_subscriber(config)

    def create_rmdx8_motors(self) -> None:
        """
        Create all necessary RMDx8 motors and add them to the dictionary
        """

        for config in MotorConfigs.get_all_motors():
            if not isinstance(config, RMDx8MotorConfig):
                continue
            self.add_motor(config)

    def _create_request(self, can_id: int, msg: String) -> None:
        """
        Add a request to the ring buffer for later dispatch
        """
        with self._buffer_lock:
            self._req_buffer.append((can_id, msg))

    def _handle_requests(self) -> None:
        """
        Drain the ring buffer and dispatch each command to the correct motor
        """
        with self._buffer_lock:
            if not self._req_buffer:
                return
            can_id, msg = self._req_buffer.popleft()
        motor = self._id_to_rmdx8_motor.get(can_id)
        if motor is None:
            self.get_logger().error(f"Received request for motor {can_id} that doesnt exist")
            return
        if msg.data == self._UPDATE_STATE:
            motor.publish_data()
        else:
            motor.data_in_callback(msg)

    def motor_count(self) -> int:
        """
        Returns the number of motors
        """
        return len(self._id_to_rmdx8_motor)


def _build_executor(nodes: Sequence[Node]) -> Executor:
    # each motor has a timer and a subscriber callback that can run at the same time, so
    # 2 threads per motor, and at least 4 or spin_once crashes
    manager = nodes[0]
    assert isinstance(manager, RMDx8MotorManager)
    return MultiThreadedExecutor(num_threads=max(2 * manager.motor_count() + 2, 4))


def _stop_motors(nodes: Sequence[Node]) -> None:
    for node in nodes:
        if isinstance(node, RMDx8MotorManager):
            node.shutdown_motors()


def main(args: list[str] | None = None) -> None:
    run_nodes(
        RMDx8MotorManager,
        args=args,
        executor_factory=_build_executor,
        on_shutdown=_stop_motors,
    )


if __name__ == "__main__":
    main(sys.argv)
