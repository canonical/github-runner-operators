#!/usr/bin/env bash

#
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
#

export ROCKCRAFT_ENABLE_EXPERIMENTAL_EXTENSIONS=true

ln -s ./garm-rockcraft.yaml ./rockcraft.yaml
rockcraft clean
rockcraft pack
rm ./rockcraft.yaml
