import launch
from launch.actions import Shutdown
from launch_ros.actions import Node

# launch's own prefix is the process name, which rcutils already prints as the node name
LINE_ONLY = "{line}"

# long enough that a node failing at startup can't spin into a tight restart loop
RESPAWN_DELAY = 5.0

# Nodes that command motors get on_exit=Shutdown(): if one dies the motors keep their last
# setpoint, so taking the graph down is better than limping on, because it SIGINTs
# can_rmdx8 and its shutdown hook stops them. Everything else is safe to restart.

can_moteus_node = Node(
    package="can_moteus",
    executable="can_moteus",
    name="can_moteus_node",
    output_format=LINE_ONLY,
    on_exit=Shutdown(),
)

drivebase_node = Node(
    package="drivebase",
    executable="drivebase",
    name="drivebase_node",
    output_format=LINE_ONLY,
    on_exit=Shutdown(),
)

# Runs as trickfire like the rest of the graph, not under sudo: FastDDS uses shared memory
# for same-host traffic and those /dev/shm segments are 0644, so a root node and a
# trickfire node discover each other and then silently exchange no data. An AF_CAN raw
# socket needs no privileges anyway, only bringing the link up does.
can_rmdx8_node = Node(
    package="can_rmdx8",
    executable="can_rmdx8",
    name="can_rmdx8_node",
    output_format=LINE_ONLY,
    on_exit=Shutdown(),
)

arm_node = Node(
    package="arm",
    executable="arm",
    name="arm_node",
    output_format=LINE_ONLY,
    on_exit=Shutdown(),
)

heartbeat_node = Node(
    package="heartbeat",
    executable="heartbeat",
    name="heartbeat_node",
    output_format=LINE_ONLY,
    on_exit=Shutdown(),
)

# Telemetry only, nothing moves if it's briefly absent.
mission_control_updater_node = Node(
    package="mission_control_updater",
    executable="mission_control_updater",
    name="mission_control_updater_node",
    output_format=LINE_ONLY,
    respawn=True,
    respawn_delay=RESPAWN_DELAY,
)

# one node per working camera, so no name= here, and respawning covers a camera that gets
# plugged in after startup
camera_node = Node(
    package="camera",
    executable="roscamera",
    output_format=LINE_ONLY,
    respawn=True,
    respawn_delay=RESPAWN_DELAY,
)

# Declared directly rather than including rosbridge's own XML launch file, so the log
# level can be set: it logs every client connect and every subscription at INFO, which was
# the bulk of the console output. The parameter names match the XML's arguments.
rosbridge_node = Node(
    package="rosbridge_server",
    executable="rosbridge_websocket",
    name="rosbridge_websocket",
    output_format=LINE_ONLY,
    parameters=[
        {
            "use_compression": True,
            "call_services_in_new_thread": True,
            "send_action_goals_in_new_thread": True,
            "default_call_service_timeout": 5.0,
        }
    ],
    arguments=["--ros-args", "--log-level", "warn"],
    respawn=True,
    respawn_delay=RESPAWN_DELAY,
)

# backs mission control's topic and service introspection. The empty globs are what
# rosbridge's XML launch file passed.
rosapi_node = Node(
    package="rosapi",
    executable="rosapi_node",
    name="rosapi",
    output_format=LINE_ONLY,
    parameters=[
        {
            "topics_glob": "",
            "services_glob": "",
            "params_glob": "",
        }
    ],
    arguments=["--ros-args", "--log-level", "warn"],
    respawn=True,
    respawn_delay=RESPAWN_DELAY,
)

# watches /viator/node_status and says once whether the rover came up
supervisor_node = Node(
    package="supervisor",
    executable="supervisor",
    name="supervisor",
    output_format=LINE_ONLY,
    respawn=True,
    respawn_delay=RESPAWN_DELAY,
)

# This is the example node. It will show ROS timers, subscribers, and publishers
# To include it in the startup, add it to the array in the generate_launch_description() method
example_node = Node(package="example_node", executable="myExampleNode", name="my_example_node")


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
            supervisor_node,
            rosbridge_node,
            rosapi_node,
        ]
    )
