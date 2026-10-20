# every target is a thin wrapper over the script of the same name in scripts/, so
# anything here can also be run directly
# comments starting with `##` are printed in `make help` keep this convention please

.PHONY: help launch tui raw build clean container connect can-setup \
	can-sudoers sync format hooks

.DEFAULT_GOAL := help

# --- running the rover ---

help: ## show this list
	@./scripts/help.py $(MAKEFILE_LIST)

launch: ## main launch method
	@./scripts/launch.py $(FLAGS)

tui: ## open tui with launch already running
	@./scripts/tui.py

raw: ## legacy ROS only launch with no tui
	@./scripts/raw.py

# --- the rover's CAN bus ---

can-setup: ## bring the CAN bus up right now, by hand
	@./scripts/can.py

can-sudoers: ## add can commands to sudoers so they dont require sudo
	@./scripts/can_sudoers.py

# --- development ---

build: ## build the ROS workspace
	@./scripts/build.py

clean: ## clean build files
	rm -rf build install log

container: ## build and attach to the rover container
	@./scripts/container.py $(FLAGS)

connect: ## attach a shell to the running rover container
	@./scripts/container.py -a

sync: ## rsync your codebase into the rover
	@./scripts/sync.py

format: ## format python, shell, markdown and json
	ruff format src scripts
	ruff check --fix src scripts
	shfmt -i 4 -s -w .devcontainer/
	npx -y prettier@latest --write "**/*.{md,json}"

hooks: ## install the pre-commit hooks
	pre-commit install
