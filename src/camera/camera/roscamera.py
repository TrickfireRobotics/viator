import glob
import re

import cv2
import rclpy.logging
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage

from lib.node_runner import multiThreaded, runNodes
from lib.status import StatusReporter

CAPTURE_PERIOD_SEC = 0.1


def _silenceOpenCvLogs() -> None:
    # a GStreamer/V4L2 warning per device probe, from OpenCV's own C++ logger, so ROS log
    # levels don't touch it. The accessor moved between OpenCV 4.x releases.
    try:
        cv2.setLogLevel(cv2.LOG_LEVEL_ERROR)
        return
    except AttributeError:
        pass

    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except AttributeError:
        # not fatal, we just get the noisy probe output back
        pass


def _videoDeviceIds() -> list[int]:
    ids = []
    for path in glob.glob("/dev/video*"):
        match = re.fullmatch(r"/dev/video(\d+)", path)
        if match is not None:
            ids.append(int(match.group(1)))
    return sorted(ids)


def getCameras() -> list[int]:
    # a camera commonly exposes more than one /dev/video* node (capture plus metadata),
    # so a device only counts if it opens and a read succeeds
    _silenceOpenCvLogs()
    logger = rclpy.logging.get_logger("camera")

    working = []
    candidates = _videoDeviceIds()

    for device_id in candidates:
        capture = cv2.VideoCapture(device_id)
        try:
            if not capture.isOpened():
                continue
            is_reading, _frame = capture.read()
            if is_reading:
                working.append(device_id)
        finally:
            capture.release()

    if not working:
        logger.error(f"no working cameras found (probed {len(candidates)} video devices)")
    else:
        logger.info(f"found {len(working)} of {len(candidates)} video devices usable: {working}")

    return working


class RosCamera(Node):
    def __init__(self, index: int, device_id: int) -> None:
        # one node name per camera: they used to share one, which collided in the graph
        super().__init__(f"camera_{index}")

        self._device_id = device_id
        # set by _buildCameraNodes on the first node only, because the status topic tracks
        # the camera module rather than each capture node
        self.status: StatusReporter | None = None
        topic_name = f"video_frames{index}"

        self._publisher = self.create_publisher(CompressedImage, topic_name, 10)

        self.cap = cv2.VideoCapture(device_id)
        if not self.cap.isOpened():
            self.get_logger().error(f"failed to open /dev/video{device_id}")
        else:
            self.get_logger().info(f"publishing /dev/video{device_id} to {topic_name}")

        self.br = CvBridge()

        self.declare_parameter("deviceId", device_id)

        self.timer = self.create_timer(CAPTURE_PERIOD_SEC, self.publishCameraFrame)

    def publishCameraFrame(self) -> None:
        ret, frame = self.cap.read()
        if ret:
            self._publisher.publish(self.br.cv2_to_compressed_imgmsg(frame))

    def destroy_node(self) -> bool:
        if self.cap is not None:
            self.cap.release()
        return super().destroy_node()


def _buildCameraNodes() -> list[RosCamera]:
    device_ids = getCameras()
    nodes = [RosCamera(index, device_id) for index, device_id in enumerate(device_ids)]

    # one report for the whole module, hung off the first node
    if nodes:
        status = StatusReporter(nodes[0], "camera")
        status.ok(f"{len(device_ids)} cameras: {device_ids}")
        nodes[0].status = status

    return nodes


def main(args: list[str] | None = None) -> None:
    # multi threaded so each camera's capture timer can run concurrently
    runNodes(_buildCameraNodes, args=args, executor_factory=multiThreaded())


if __name__ == "__main__":
    main()
