.PHONY: build launch container connect can-setup sync-orin format hooks

build:
	./scripts/build.sh

launch:
	./scripts/launch.sh

container:
	./scripts/container-launch.sh $(filter-out $@,$(MAKECMDGOALS))

connect:
	./scripts/connect-to-container.sh

can-setup:
	./scripts/setup-can-network.sh

sync-orin:
	./scripts/sync-to-orin.sh $(IP) $(REMOTE_PATH)

format:
	ruff format src
	ruff check --fix src
	shfmt -i 4 -s -w scripts/ .devcontainer/
	npx -y prettier@latest --write "**/*.{md,json}"

hooks:
	pre-commit install
