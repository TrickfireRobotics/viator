# Contributing

## Development Environment

Development happens inside the provided devcontainer. Open the repo in VS Code with the
[Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
installed, then choose **Reopen in Container** when prompted. This ensures everyone builds
and runs the project with the same tools and dependencies.

## Code Style

- Formatting is enforced by `make format`, which runs:
    - [ruff](https://docs.astral.sh/ruff/) to format and lint Python code in `src`
    - [shfmt](https://github.com/mvdan/sh) to format shell scripts in `scripts/` and `.devcontainer/`
    - [Prettier](https://prettier.io/) to format Markdown and JSON files
- Run `make format` before committing, or let your editor format on save
- Keep changes consistent with the formatting these tools apply — don't hand-format
  differently from what they produce

## Commits & PRs

- Keep commits focused and descriptive
- Make sure your code is formatted before opening a pull request
