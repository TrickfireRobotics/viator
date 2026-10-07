from rclpy.node import Node
from std_msgs.msg import String

from lib.color_codes import ColorCodes, colorStr
from lib.configs import MotorConfigs
from lib.interface.robot_info import RobotInfo
from lib.node_runner import runNodes

from . import info_to_json_helper


class MissionControlUpdater(Node):
    def __init__(self) -> None:
        super().__init__("mission_control_updater_node")
        self.get_logger().info(
            colorStr("Launching mission_control_updater_node", ColorCodes.BLUE_OK)
        )

        self.publisher_to_mc = self.create_publisher(String, "mission_control_updater", 1)

        self.timer = self.create_timer(0.01, self.sendData)
        self.robot_info = RobotInfo(self)

    def sendData(self) -> None:
        json_builder = info_to_json_helper.InfoToJSONHelper()

        for motor in MotorConfigs.getAllMotors():
            json_builder.addMoteusEntry(self.robot_info.getMotorState(motor))

        msg = String()
        msg.data = json_builder.buildJSONString()
        self.publisher_to_mc.publish(msg)


def main(args: list[str] | None = None) -> None:
    """
    The entry point of the node.
    """

    runNodes(MissionControlUpdater, args=args)


if __name__ == "__main__":
    main()
