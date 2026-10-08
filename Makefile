# Every target is a thin wrapper over a script in scripts/, so anything here can also be
# run directly. Comments starting with `##` become the `make help` listing.

.PHONY: help launch stop status tui graph build clean container connect can-setup sync \
	format hooks runtime save load deploy preflight

.DEFAULT_GOAL := help

# --- running the rover ---

help: ## show this list
	@./scripts/help.sh $(MAKEFILE_LIST)

launch: ## bring everything up and open the dashboard (the one you want)
	@./scripts/launch.sh $(FLAGS)

stop: ## stop the node graph
	@./scripts/stop.sh $(FLAGS)

status: ## check the rover is actually ready
	@./scripts/preflight.sh

tui: ## open the dashboard against a rover that is already running
	@./scripts/tui.sh

graph: ## run the node graph alone, in the foreground (no dashboard)
	@./scripts/graph.sh

# --- development ---

build: ## build the ROS 2 workspace
	@./scripts/build.sh

clean: ## delete colcon's build output
	rm -rf build install log

container: ## build and attach to the dev container
	@./scripts/container-launch.sh $(FLAGS)

connect: ## attach a shell to the running dev container
	@./scripts/connect-to-container.sh

can-setup: ## bring the CAN bus up by hand
	@./scripts/setup-can-network.sh

sync: ## rsync this checkout to the rover (IP=, REMOTE_PATH=)
	@./scripts/sync-to-orin.sh

format: ## format python, shell, markdown and json
	ruff format src
	ruff check --fix src
	shfmt -i 4 -s -w scripts/ .devcontainer/ deploy/
	npx -y prettier@latest --write "**/*.{md,json}"

hooks: ## install the pre-commit hooks
	pre-commit install

# --- deployment ---

runtime: ## build the self-contained runtime image
	@./scripts/build-runtime.sh

save: ## write the runtime image to a tarball (OUT=)
	@./scripts/save-image.sh $(OUT)

load: ## load a runtime image tarball (ARCHIVE=)
	@./scripts/load-image.sh $(ARCHIVE)

deploy: ## install the compose file and systemd units on this machine
	sudo ./scripts/install-deploy.sh

preflight: status ## alias for status
