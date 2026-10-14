# every target is a thin wrapper over the script of the same name in scripts/, so
# anything here can also be run directly
# comments starting with `##` are printed in `make help` keep this convention please

.PHONY: help launch tui raw build clean container connect can-setup \
	can-sudoers sync format hooks

.DEFAULT_GOAL := help

# --- running the rover ---

help: ## show this list
	@./scripts/help.sh $(MAKEFILE_LIST)

launch: ## main launch method
	@./scripts/launch.sh $(FLAGS)

tui: ## open tui with launch already running
	@./scripts/tui.sh

raw: ## legacy ROS only launch with no tui
	@./scripts/raw.sh

# --- the rover's CAN bus ---

can-setup: ## bring the CAN bus up right now, by hand
	@./scripts/can.sh

can-sudoers: ## add can commands to sudoers so they dont require sudo
	@./scripts/can-sudoers.sh

# --- development ---

build: ## build the ROS workspace
	@./scripts/build.sh

clean: ## clean build files
	rm -rf build install log

container: ## build and attach to the rover container
	@./scripts/container.sh $(FLAGS)

connect: ## attach a shell to the running rover container
	@./scripts/container.sh -a

sync: ## rsync your codebase into the rover
	@./scripts/sync.sh

format: ## format python, shell, markdown and json
	ruff format src
	ruff check --fix src
	shfmt -i 4 -s -w scripts/ .devcontainer/
	npx -y prettier@latest --write "**/*.{md,json}"

hooks: ## install the pre-commit hooks
	pre-commit install
