# Viator

Software developed by [Trickfire Robotics](https://www.trickfirerobotics.org/) for the Viator Rover built for the [University Rover Challenge](https://urc.marssociety.org/).

## Running it

One command, from the repo root, on the rover or on your own machine:

```bash
make launch
```

It checks the host, brings the CAN bus up, builds the container and the ROS 2 workspace, starts the node graph, and leaves you in the dashboard. `make` on its own lists every other target.

## Documentation

**Full documentation is at [docs.trickfirerobotics.com/viator](https://docs.trickfirerobotics.com/viator).**

- [Getting Started](https://docs.trickfirerobotics.com/viator/getting-started) - dev environment setup
- [Launching the Rover](https://docs.trickfirerobotics.com/viator/launching) - the one command and everything around it
- [The Dashboard](https://docs.trickfirerobotics.com/viator/dashboard) - how to read and drive the terminal UI
- [Architecture](https://docs.trickfirerobotics.com/viator/architecture) - architecture decisions and explanations
- [Deploying to the Rover](https://docs.trickfirerobotics.com/viator/deployment) - the competition image and systemd
