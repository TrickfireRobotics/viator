# Contributing

## Development Environment

For editor integration, open the repo in VS Code with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) installed and choose **Reopen in Container** when prompted. Either way you get the same ROS 2 Humble environment everyone else builds and runs against.

See [Launching the Rover](https://docs.trickfirerobotics.com/viator/launching) for the full workflow.

## Code Style

- Formatting is enforced by `make format`, which runs:
    - [ruff](https://docs.astral.sh/ruff/) to format and lint Python code in `src` and `scripts`
    - [shfmt](https://github.com/mvdan/sh) to format shell scripts in `.devcontainer/`
- Run `make format` before committing, or let your editor format on save
- Keep changes consistent with the formatting these tools apply — don't hand-format
  differently from what they produce

## Commits & PRs

- Keep commits focused and descriptive
- Make sure your code is formatted before opening a pull request
