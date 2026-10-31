SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c

.DELETE_ON_ERROR:
MAKEFLAGS += --no-print-directory

.PHONY: help submodules launch build clean container connect can-setup can-sudoers sync \
	format lint

.DEFAULT_GOAL := help

ifndef NO_COLOR
BOLD := \033[1m
DIM := \033[2m
GREEN := \033[0;32m
OFF := \033[0m
endif

# --- main ---

help: ## show this help
	@printf "$(BOLD)viator:$(OFF) make targets\n"
	@awk 'BEGIN { FS = ":.*## " } \
		/^# --- / { gsub(/^# --- | ---$$/, ""); printf "\n$(BOLD)%s$(OFF)\n", $$0; next } \
		/^[a-zA-Z0-9_-]+:.*## / { printf "  $(GREEN)make %-12s$(OFF) $(DIM)%s$(OFF)\n", $$1, $$2 }' \
		$(MAKEFILE_LIST)


submodules: ## pull git submodules
	@git submodule update --init --recursive


launch: ## rover launch
	@./scripts/launch.py $(FLAGS)

# --- can ---

can-setup: ## bring the CAN bus up right now, by hand
	@./scripts/can.py $(FLAGS)

can-sudoers: ## add can commands to sudoers so they dont require sudo
	@./scripts/can_sudoers.py

# --- development ---

build: ## build the ROS workspace
	@./scripts/build.py $(FLAGS)

clean: ## remove build output, logs and recorded bags
	rm -rf $(CURDIR)/build $(CURDIR)/install $(CURDIR)/log

container: ## build and attach to the rover container
	@./scripts/container.py $(FLAGS)

connect: ## attach a shell to the running rover container
	@./scripts/container.py --attach

sync: ## rsync your codebase into the rover
	@./scripts/sync.py $(FLAGS)

format: ## format and autofix python
	ruff format src scripts
	ruff check --fix src scripts

lint: ## typecheck
	ruff check --output-format=full src scripts
	ruff format --check src scripts
	mypy src scripts
