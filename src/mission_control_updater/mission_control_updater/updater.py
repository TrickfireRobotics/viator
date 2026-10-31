from rclpy.node import Node
from std_msgs.msg import String

from lib.configs import MotorConfigs
from lib.interface.robot_info import RobotInfo
from lib.node_runner import run_nodes
from lib.status import StatusReporter
from mission_control_updater import info_to_json_helper


class MissionControlUpdater(Node):
    def __init__(self) -> None:
        super().__init__("mission_control_updater_node")

        self.publisher_to_mc = self.create_publisher(String, "mission_control_updater", 1)

        self.timer = self.create_timer(0.01, self.send_data)
        self.robot_info = RobotInfo(self)

        self._status = StatusReporter(self, "mission_control_updater")
        self._status.ok()

    def send_data(self) -> None:
        json_builder = info_to_json_helper.InfoToJSONHelper()

        for motor in MotorConfigs.get_all_motors():
            json_builder.add_moteus_entry(self.robot_info.get_motor_state(motor))

        msg = String()
        msg.data = json_builder.build_json_string()
        self.publisher_to_mc.publish(msg)


def main(args: list[str] | None = None) -> None:
    run_nodes(MissionControlUpdater, args=args)


if __name__ == "__main__":
    main()
