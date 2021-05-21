NAME := ska-sdp-helmdeploy
VERSION := $(patsubst "%",%, $(shell awk -F' = ' '/^__version__ =/{print $$2}' src/ska_sdp_helmdeploy/version.py))

include make/Makefile

release-patch: ## Patch release; -n --> do not synchronize tags from git
	bumpver update --patch -n

release-minor: ## Minor release; -n --> do not synchronize tags from git
	bumpver update --minor -n

release-major: ## Major release; -n --> do not synchronize tags from git
	bumpver update --major -n