.PHONY: build clean launch tui container connect can-setup sync format hooks \
	runtime save load deploy preflight

build:
	./scripts/build.sh

clean:
	rm -rf build install log

launch:
	./scripts/launch.sh

tui:
	./scripts/tui.sh

# --- deployment ---

runtime:
	./scripts/build-runtime.sh

save:
	./scripts/save-image.sh $(OUT)

load:
	./scripts/load-image.sh $(ARCHIVE)

deploy:
	sudo ./scripts/install-deploy.sh

preflight:
	./scripts/preflight.sh

# --- development ---

container:
	./scripts/container-launch.sh $(filter-out $@,$(MAKECMDGOALS))

connect:
	./scripts/connect-to-container.sh

can-setup:
	./scripts/setup-can-network.sh

sync:
	./scripts/sync-to-orin.sh $(IP) $(REMOTE_PATH)

format:
	ruff format src
	ruff check --fix src
	shfmt -i 4 -s -w scripts/ .devcontainer/ deploy/
	npx -y prettier@latest --write "**/*.{md,json}"

hooks:
	pre-commit install
