from threading import Lock

import std_msgs.msg
from moteus.moteus import Result
from rclpy.node import Node
from rclpy.publisher import Publisher
from rclpy.subscription import Subscription
from std_msgs.msg import String

from lib.configs import MoteusMotorConfig
from lib.motor_state.moteus_motor_state import MoteusMotorState, MoteusRunSettings


class MoteusMotor:
    def __init__(self, config: MoteusMotorConfig, ros_node: Node) -> None:
        """
        Create a logical representation of a motor that is using
        a Moteus controller. Contains a list of variables that should be
        sent to the Moteus controller. Subscribes to input and publishes output

        Paramaters
        -------
        config : MoteusMotorConfig
            The config of the motor.
        rosNode : Node
            The ROS node used to create the ros_moteus_bridge.py
        """

        self.config = config
        self._ros_node = ros_node

        self._subscriber = self._createSubscriber()
        self._publisher = self._createPublisher()

        # Mutex - used to protect writing/reading the state of the motor
        self.mutex_lock = Lock()

        # The settings we can send to the moteus controller
        # using the make_position() method
        self.run_settings: MoteusRunSettings = MoteusRunSettings()

        # By default, the motor is shutoff
        self.set_stop = True

    def _createSubscriber(self) -> Subscription:
        """
        The subscriber to get data from.
        The format of the topic is the following: moteusmotor_<can_id>_from_interface
        """
        topic_name = self.config.getInterfaceTopicName()
        subscriber = self._ros_node.create_subscription(
            std_msgs.msg.String,
            topic_name,
            self.dataInCallback,
            1,  # Size of queue is 1. All additional ones are dropped
        )

        return subscriber

    def _createPublisher(self) -> Publisher:
        """
        The publisher to send data to.
        The format of the topic is the following: moteusmotor_<can_id>_from_can
        """
        topic_name = self.config.getCanTopicName()
        # Size of queue is 1. All additional ones are dropped
        publisher = self._ros_node.create_publisher(std_msgs.msg.String, topic_name, 1)

        return publisher

    def dataInCallback(self, msg: String) -> None:
        """
        Update the motor state. Mutex protected,
        meaning that no one can go into any other "critical section"
        of code that also has a mutex protecting it.
        """
        with self.mutex_lock:
            self.run_settings = MoteusRunSettings.fromJsonMsg(msg)

    def publishData(self, moteus_data: Result) -> None:
        """
        Publishes the data from the moteus controller
        """
        with self.mutex_lock:
            try:
                if not self._ros_node.context.ok():
                    return

                # self._rosNode.get_logger().info(str(moteusData.values))

                # TODO: We need to update firmware to get POWER information (7/1/2024)
                # https://github.com/mjbots/moteus/releases
                # https://discord.com/channels/633996205759791104/722434939676786688/1252380387783610428
                # self._rosNode.get_logger().info(str(moteusData.values.keys()))

                state = MoteusMotorState.fromMoteusData(self.config.can_id, moteus_data)
                self._publisher.publish(state.toMsg())
            except Exception as error:  # pylint: disable=broad-exception-caught
                # This is used to handle any errors in order to prevent the thread from dying
                # Specifically, when we crtl-c we want the motors to be set_stop(), but if this
                # thread crashes we cannot do that. So we catch any errors
                self._ros_node.get_logger().info("Failed to publish motor data")
                self._ros_node.get_logger().info(str(error))
