<p align="center">
  <a href="https://www.trickfirerobotics.org/">
    <img src="https://raw.githubusercontent.com/TrickFireRobotics/simulations/main/assets/trickfire-logo.png" width="280" alt="TrickFire Robotics">
  </a>
</p>

<h1 align="center">Viator</h1>

<p align="center">
  Rover software for TrickFire Robotics' University Rover Challenge platform.
</p>

<p align="center">
  <a href="https://trickfirerobotics.com">Website</a>
  ·
  <a href="https://docs.trickfirerobotics.com/viator">Documentation</a>
  ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

Viator is the ROS 2 Humble code that runs the rover: its drivebase, arm, cameras, CAN motor
controllers, supervision, and the interfaces between them. It is built to run in the same Docker
environment on a developer machine and on the rover.

The repository is intentionally not a second manual. The operational detail lives in the docs,
where it can stay current without turning this page into a wall of setup instructions.

| If you need to…                                   | Start here                                                                   |
| ------------------------------------------------- | ---------------------------------------------------------------------------- |
| Set up a checkout or dev container                | [Getting started](https://docs.trickfirerobotics.com/viator/getting-started) |
| Bring the rover up or inspect a running system    | [Launching the rover](https://docs.trickfirerobotics.com/viator/launching)   |
| Understand the ROS packages and deployment layout | [Architecture](https://docs.trickfirerobotics.com/viator/architecture)       |
| Change the code                                   | [Contributing](CONTRIBUTING.md)                                              |

## Around the project

- `src/` contains the ROS packages and shared rover libraries.
- `scripts/` contains the commands behind the day-to-day `make` targets.
- `.devcontainer/` defines the reproducible ROS 2 development and rover environments.
- `docs/` is the source for the published Viator documentation.

Run `make` at the repository root for the local command list. For an overview of TrickFire Robotics
and the team behind Viator, visit [trickfirerobotics.org](https://www.trickfirerobotics.org/).
