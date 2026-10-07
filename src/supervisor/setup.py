from setuptools import find_packages, setup

package_name = "supervisor"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="trickfire",
    maintainer_email="matysta@outlook.com",
    description="Collects per-node health reports and summarises rover readiness.",
    license="TODO: License declaration",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": ["supervisor = supervisor.supervisor:main"],
    },
)
