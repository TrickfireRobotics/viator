import launch
from launch.actions import Shutdown
from launch_ros.actions import Node

# launch prefixes every output line with the process name, which just duplicates the node
# name rcutils already prints. Keep rcutils' copy and drop launch's.
LINE_ONLY = "{line}"

# How long to wait before bringing a crashed node back. Long enough that a node failing
# at startup can't spin into a tight restart loop.
RESPAWN_DELAY = 5.0

# Nodes that command motors are launched with on_exit=Shutdown(). If one of them dies the
# motors keep whatever setpoint they were last given, so limping along without it is worse
# than stopping: taking the whole graph down SIGINTs can_rmdx8, whose shutdown hook stops
# the motors. Everything else is safe to simply restart.

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

# Runs as root via sudo: opening the raw CAN socket for can1 needs CAP_NET_RAW/NET_ADMIN,
# which the non-root trickfire user doesn't have (see .devcontainer/trickfire-can-sudoers).
can_rmdx8_node = Node(
    package="can_rmdx8",
    executable="can_rmdx8",
    name="can_rmdx8_node",
    prefix="sudo -n --",
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

# One node per working camera, so no name= here. Respawning also covers the case where no
# camera was present at startup and one gets plugged in later.
camera_node = Node(
    package="camera",
    executable="roscamera",
    output_format=LINE_ONLY,
    respawn=True,
    respawn_delay=RESPAWN_DELAY,
)

# Previously an IncludeLaunchDescription of rosbridge's own XML launch file. Declaring the
# nodes directly means we can set their log level: rosbridge logs every client connect and
# every topic subscription at INFO, which was the bulk of the console output. The parameter
# names match the launch arguments the XML accepted.
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

# rosapi backs mission control's topic and service introspection. The globs are passed
# explicitly as empty strings, which is what rosbridge's XML launch file did.
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

# Watches /viator/node_status and prints one readable readiness summary. Purely an
# observer, so it is safe to restart.
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
