import os
from glob import glob

from setuptools import setup

package_name = "can_moteus"

setup(
    name=package_name,
    version="0.0.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name), glob("launch/*launch.[pxy][yma]*")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="trickfire",
    maintainer_email="tfrbtcs@uw.edu",
    description="Controls Moteus motor controllers over CAN",
    license="Apache-2.0",
    entry_points={
        "console_scripts": ["can_moteus = can_moteus.ros_moteus_bridge:main"],
    },
)
