from glob import glob

from setuptools import setup

package_name = "viator_launch"

setup(
    name=package_name,
    version="0.0.0",
    packages=[],
    data_files=[
        # Register this package in the ament resource index.
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    # Zip-safety is not yet confirmed.
    zip_safe=True,
    maintainer="trickfire",
    maintainer_email="phillipov@outlook.com",
    description="TODO: Package description",
    license="TODO: License declaration",
    tests_require=["pytest"],
)
