# every target is a thin wrapper over the script of the same name in scripts/, so
# anything here can also be run directly
# comments starting with `##` are printed in `make help` keep this convention please

.PHONY: help launch status logs build clean container connect can-setup \
	can-sudoers sync format

.DEFAULT_GOAL := help

# --- running the rover ---

help: ## show this list
	@./scripts/help.py $(MAKEFILE_LIST)

launch: ## bring the rover up and stream its output here
	@./scripts/launch.py $(FLAGS)

# exits non-zero when the rover isn't ready, which is useful to a script and looks like
# a broken build here, so only the script keeps the code
status: ## print what every module says about itself (FLAGS=-w to keep watching)
	@./scripts/status.py $(FLAGS) || true

logs: ## follow the launch output of a rover thats already running
	@./scripts/logs.py

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
