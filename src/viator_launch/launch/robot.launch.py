import os

import launch
from ament_index_python import get_package_share_directory
from launch.actions import IncludeLaunchDescription
from launch_ros.actions import Node
from launch_xml.launch_description_sources import XMLLaunchDescriptionSource

can_moteus_node = Node(package="can_moteus", executable="can_moteus", name="can_moteus_node")
drivebase_node = Node(package="drivebase", executable="drivebase", name="drivebase_node")

# Runs as root via sudo: opening the raw CAN socket for can1 needs CAP_NET_RAW/NET_ADMIN,
# which the non-root trickfire user doesn't have (see .devcontainer/trickfire-can-sudoers).
can_rmdx8_node = Node(
    package="can_rmdx8",
    executable="can_rmdx8",
    name="can_rmdx8_node",
    prefix="sudo -n --",
)

mission_control_updater_node = Node(
    package="mission_control_updater",
    executable="mission_control_updater",
    name="mission_control_updater_node",
)

arm_node = Node(package="arm", executable="arm", name="arm_node")

heartbeat_node = Node(package="heartbeat", executable="heartbeat", name="heartbeat_node")

camera_node = Node(package="camera", executable="roscamera", name="camera_node")

# This is the example node. It will show ROS timers, subscribers, and publishers
# To include it in the startup, add it to the array in the generate_launch_description() method
example_node = Node(package="example_node", executable="myExampleNode", name="my_example_node")

launch_include = IncludeLaunchDescription(
    XMLLaunchDescriptionSource(
        os.path.join(
            get_package_share_directory("rosbridge_server"), "launch/rosbridge_websocket_launch.xml"
        ),
    ),
    launch_arguments=[
        ("use_compression", "true"),
        ("call_services_in_new_thread", "true"),
        ("send_action_goals_in_new_thread", "true"),
        ("default_call_service_timeout", "5.0"),
    ],
)


def generate_launch_description() -> launch.LaunchDescription:  # pylint: disable=invalid-name
    return launch.LaunchDescription(
        [
            # can_moteus_node, (dsabeled for now cause arm is not implemented)
            drivebase_node,
            can_rmdx8_node,
            mission_control_updater_node,
            arm_node,
            heartbeat_node,
            camera_node,
            launch_include,
        ]
    )
