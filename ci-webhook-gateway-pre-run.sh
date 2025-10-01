!/usr/bin/env bash
#
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#

# This is a workaround, because we will have multiple *_rockcraft.yaml files and  rockcraft is
# not supporting building rocks when there is no rockcraft.yaml file with that exact name in the repo root and operator workflows
# is not building rocks if there is a rockcraft.yaml after the plan job.
# So we need to build the rock here and push it to ghcr.io, so pytest can use it in the tests.
# This script assumes that GITHUB_TOKEN are set in the environment.

IMAGE_NAME="webhook-gateway"

sudo snap install rockcraft --classic --channel=latest/edge
bash ./build-webhook-gateway-rock.sh
image="ghcr.io/${GITHUB_REPOSITORY_OWNER}/${IMAGE_NAME}:${GITHUB_SHA}"
rockfile=`ls ./webhook-gateway_*.rock | head -n 1`
sudo  /snap/rockcraft/current/bin/skopeo --insecure-policy copy \
                --dest-creds="${GITHUB_ACTOR}:${GITHUB_TOKEN}" \
                "oci-archive:${rockfile} \
                "docker://${image}"
echo "PYTESTADDOPTS=--webhook-gateway-image ${image}" >> $GITHUB_ENV
