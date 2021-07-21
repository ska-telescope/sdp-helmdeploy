NAME := ska-sdp-helmdeploy
VERSION := $(shell sed -ne 's/^__version__ = "\(.*\)"/\1/p' src/ska_sdp_helmdeploy/version.py)

include make/help.mk
include make/docker.mk
include make/release.mk
