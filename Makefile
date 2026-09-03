.PHONY: init validate version bump release destroy clean help

PROJECT_ROOT := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))

help:
	@echo "Scaffold Template Commands:"
	@echo "  init         Idempotent init"
	@echo "  validate     Project integrity check"
	@echo "  version      Show current version"
	@echo "  bump         Bump minor version"
	@echo "  release      Create git tag"
	@echo "  destroy      Idempotent cleanup"
	@echo "  help         Show this help"

init:
	@echo "=== Initialisation ==="
	@bash $(PROJECT_ROOT)/scripts/setup.sh
	@bash $(PROJECT_ROOT)/scripts/validate.sh

validate:
	@echo "=== Validation ==="
	@bash $(PROJECT_ROOT)/scripts/validate.sh

version:
	@bash $(PROJECT_ROOT)/scripts/version.sh get

bump:
	@echo "=== Bump ==="
	@bash $(PROJECT_ROOT)/scripts/version.sh bump minor
	@bash $(PROJECT_ROOT)/scripts/version.sh get

release:
	@echo "=== Release ==="
	@bash $(PROJECT_ROOT)/scripts/version.sh tag
	@echo "Done"

destroy:
	@echo "=== Cleanup ==="
	@bash $(PROJECT_ROOT)/scripts/destroy.sh

clean: destroy
