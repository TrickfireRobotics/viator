# Contributing

## Development Environment

Development happens inside the provided container. The quickest way in is from the repo root:

```bash
make launch   # builds the container, builds the workspace, runs the rover
make connect  # just a shell in the container
make          # lists every target
```

For editor integration, open the repo in VS Code with the
[Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
installed and choose **Reopen in Container** when prompted. Either way you get the same
ROS 2 Humble environment everyone else builds and runs against.

See [Launching the Rover](https://docs.trickfirerobotics.com/viator/launching) for the full
workflow.

## Code Style

- Formatting is enforced by `make format`, which runs:
    - [ruff](https://docs.astral.sh/ruff/) to format and lint Python code in `src`
    - [shfmt](https://github.com/mvdan/sh) to format shell scripts in `scripts/`, `.devcontainer/` and `deploy/`
    - [Prettier](https://prettier.io/) to format Markdown and JSON files
- Run `make format` before committing, or let your editor format on save
- Keep changes consistent with the formatting these tools apply — don't hand-format
  differently from what they produce

Run `make hooks` once after cloning to install the pre-commit hooks that enforce this
automatically at commit time.

## Commits & PRs

- Keep commits focused and descriptive
- Make sure your code is formatted before opening a pull request
