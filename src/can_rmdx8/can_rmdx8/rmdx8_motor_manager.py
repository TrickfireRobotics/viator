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

from lib.color_codes import ColorCodes, colorStr
from lib.configs import MotorConfigs, RMDx8MotorConfig
from lib.node_runner import runNodes
from lib.status import StatusReporter

from .can_health import CanHealth
from .rmdx8_motor import RMDx8Motor


class RMDx8MotorManager(Node):
    """
    Class to manage the control and storage of RMDx8 motors in the ROS system.
    """

    # String identifier for updating motor state
    _UPDATE_STATE = "UPDATE_STATE"

    def __init__(self) -> None:
        super().__init__("can_rmdx8_node")
        self.get_logger().info(colorStr("Launching can_rmdx8 node", ColorCodes.BLUE_OK))
        self._id_to_rmdx8_motor: dict[int, RMDx8Motor] = {}
        self.driver = rmd.CanDriver("can1")
        self._driver_lock = Lock()
        self._req_buffer: deque[tuple[int, String]] = deque(maxlen=1000)
        self._buffer_lock = Lock()
        self.health = CanHealth(self)
        self.createRMDx8Motors()
        # Hardware testing
        self.create_timer(0.005, self._handleRequests)

        self._status = StatusReporter(self, "can_rmdx8")
        self._status.ok(f"{self.motorCount()} motors on can1")
        self.health.setStatusReporter(self._status, f"{self.motorCount()} motors on can1")
        self.get_logger().info(f"can_rmdx8 ready, {self.motorCount()} motors on can1")

    def _createSubscriber(self, config: RMDx8MotorConfig) -> Subscription:
        can_id = config.can_id
        return self.create_subscription(
            std_msgs.msg.String,
            config.getInterfaceTopicName(),
            # We pass the create_request lambda with the
            # capture clause as the motor_id's can id
            # so we know who is making the requests
            lambda msg: self._createRequest(can_id, msg),
            1,
            callback_group=ReentrantCallbackGroup(),
        )

    def shutdownMotors(self) -> None:
        """
        Shutdown all motors
        """
        for motor in self._id_to_rmdx8_motor.values():
            motor.shutdownMotor()

    def addMotor(self, config: RMDx8MotorConfig) -> None:
        """
        Adds new rmdx8 motor to the motor dictionary
        """

        motor = RMDx8Motor(
            config,
            self.driver,
            self,
            lambda: self._createRequest(config.can_id, String(data=self._UPDATE_STATE)),
            self._driver_lock,
            self.health,
        )
        self._id_to_rmdx8_motor[config.can_id] = motor
        self._createSubscriber(config)

    def createRMDx8Motors(self) -> None:
        """
        Create all necessary RMDx8 motors and add them to the dictionary
        """

        for config in MotorConfigs.getAllMotors():
            if not isinstance(config, RMDx8MotorConfig):
                continue
            self.addMotor(config)

    def _createRequest(self, can_id: int, msg: String) -> None:
        """
        Add a request to the ring buffer for later dispatch
        """
        with self._buffer_lock:
            self._req_buffer.append((can_id, msg))

    def _handleRequests(self) -> None:
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
            motor.publishData()
        else:
            motor.dataInCallback(msg)

    def motorCount(self) -> int:
        """
        Returns the number of motors
        """
        return len(self._id_to_rmdx8_motor)


def _buildExecutor(nodes: Sequence[Node]) -> Executor:
    """
    Each motor has a timer + subscriber callback that can run concurrently, so allocate
    2 threads per motor with a minimum of 4 to avoid spin_once crashes.
    """
    manager = nodes[0]
    assert isinstance(manager, RMDx8MotorManager)
    return MultiThreadedExecutor(num_threads=max(2 * manager.motorCount() + 2, 4))


def _stopMotors(nodes: Sequence[Node]) -> None:
    """
    Brings the motors to a stop before the node is torn down.
    """
    for node in nodes:
        if isinstance(node, RMDx8MotorManager):
            node.shutdownMotors()


# Main function
def main(args: list[str] | None = None) -> None:
    """
    The entry point for RMDx8
    """

    runNodes(
        RMDx8MotorManager,
        args=args,
        executor_factory=_buildExecutor,
        on_shutdown=_stopMotors,
    )


# If script is run directly, then create a RMDx8MotorManager object and run the main function
if __name__ == "__main__":
    main(sys.argv)
