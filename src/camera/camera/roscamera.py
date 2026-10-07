import glob
import re

import cv2  # OpenCV library
import rclpy.logging
from cv_bridge import CvBridge  # Package to convert between ROS and OpenCV Images
from rclpy.node import Node  # Handles the creation of nodes
from sensor_msgs.msg import CompressedImage  # Image is the message type

from lib.node_runner import multiThreaded, runNodes

CAPTURE_PERIOD_SEC = 0.1


def _silenceOpenCvLogs() -> None:
    """
    Stops OpenCV's C++ logger printing a GStreamer/V4L2 warning for every device probe.

    These come from OpenCV itself rather than rclpy, so ROS log levels don't touch them.
    The accessor moved between OpenCV 4.x releases, so try both spellings.
    """
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
    """
    Returns the numbers of the `/dev/video*` nodes that actually exist, in order.

    The old implementation walked indices upward until six consecutive failures, which
    meant opening half a dozen devices that were never there and printing an OpenCV
    warning for each. Asking the filesystem first means we only probe real hardware.
    """
    ids = []
    for path in glob.glob("/dev/video*"):
        match = re.fullmatch(r"/dev/video(\d+)", path)
        if match is not None:
            ids.append(int(match.group(1)))
    return sorted(ids)


def getCameras() -> list[int]:
    """
    Returns the device ids of every camera that exists and delivers a frame.

    Cameras commonly expose more than one `/dev/video*` node (a capture node plus a
    metadata node), so existing on disk isn't enough. A device only counts if it opens
    and a read succeeds.
    """
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
            # the old probe never released these, leaking a file descriptor per device
            capture.release()

    if not working:
        logger.error(f"no working cameras found (probed {len(candidates)} video devices)")
    else:
        logger.info(f"found {len(working)} of {len(candidates)} video devices usable: {working}")

    return working


class RosCamera(Node):
    def __init__(self, index: int, device_id: int) -> None:
        # Each camera gets its own node name. They used to share one, which collided in
        # the graph and made per-node parameters ambiguous.
        super().__init__(f"camera_{index}")

        self._device_id = device_id
        topic_name = f"video_frames{index}"

        # Create the publisher. This publisher will publish an Image
        # to the video_frames topic. The queue size is 10 messages.
        self._publisher = self.create_publisher(CompressedImage, topic_name, 10)

        # Create a VideoCapture object
        self.cap = cv2.VideoCapture(device_id)
        if not self.cap.isOpened():
            self.get_logger().error(f"failed to open /dev/video{device_id}")
        else:
            self.get_logger().info(f"publishing /dev/video{device_id} to {topic_name}")

        # Used to convert between ROS and OpenCV images
        self.br = CvBridge()

        self.declare_parameter("deviceId", device_id)

        self.timer = self.create_timer(CAPTURE_PERIOD_SEC, self.publishCameraFrame)

    def publishCameraFrame(self) -> None:
        """
        Callback function publishes a frame captured from a camera to /video_framesX (X is specific
        camera ID) every 0.1 seconds
        """

        # Capture frame-by-frame
        # This method returns True/False as well as the video frame.
        ret, frame = self.cap.read()

        if ret:
            # Publish the image.
            self._publisher.publish(self.br.cv2_to_compressed_imgmsg(frame))

    def destroy_node(self) -> bool:
        """
        Releases the capture device before tearing the node down.
        """
        if self.cap is not None:
            self.cap.release()
        return super().destroy_node()


def _buildCameraNodes() -> list[RosCamera]:
    """
    Builds one node per working camera, numbered by publish order rather than device id.
    """
    return [RosCamera(index, device_id) for index, device_id in enumerate(getCameras())]


def main(args: list[str] | None = None) -> None:
    """
    The entry point of the node.
    """

    # a MultiThreadedExecutor so each camera's capture timer can run concurrently
    runNodes(_buildCameraNodes, args=args, executor_factory=multiThreaded())


if __name__ == "__main__":
    main()
