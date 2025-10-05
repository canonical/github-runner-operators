#!/usr/bin/env bash

#
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#

export ROCKCRAFT_ENABLE_EXPERIMENTAL_EXTENSIONS=true

ln -s ./webhook-gateway-rockcraft.yaml ./rockcraft.yaml
rockcraft clean
rockcraft pack
rm ./rockcraft.yaml
