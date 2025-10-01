#!/usr/bin/env bash
#
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#

# This is a workaround, because we will have multiple *_rockcraft.yaml files and  rockcraft is
# not supporting building rocks when there is no rockcraft.yaml file with that exact name in the repo root and operator workflows
# is not building rocks if there is a rockcraft.yaml after the plan job.
# So we need to build the rock here and push it to ghcr.io, so pytest can use it in the tests.

IMAGE_NAME="webhook-gateway"

sudo snap install rockcraft --classic --channel=latest/edge
bash ./build-webhook-gateway-rock.sh
image="localhost:32000/${IMAGE_NAME}:latest"
rockfile=`ls ./webhook-gateway_*.rock | head -n 1`
sudo  /snap/rockcraft/current/bin/skopeo --insecure-policy copy \
                --dest-tls-verify=false \
                "oci-archive:${rockfile}" \
                "docker://${image}"
echo "PYTEST_ADDOPTS=--webhook-gateway-image ${image}" >> $GITHUB_ENV
