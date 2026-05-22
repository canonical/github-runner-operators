#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""GARM charm entrypoint."""

import logging
import typing

import ops
import tomli_w

logger = logging.getLogger(__name__)

GARM_CONFIG_PATH: typing.Final[str] = "/srv/garm/config/config.toml"
GARM_SECRETS_LABEL: typing.Final[str] = "garm-secrets"
CONTAINER_NAME: typing.Final[str] = "app"
PEBBLE_SERVICE_NAME: typing.Final[str] = "app"
GARM_BINARY: typing.Final[str] = "/usr/local/bin/garm"
OPENSTACK_PROVIDER_BINARY: typing.Final[str] = "/usr/local/bin/garm-provider-openstack"


def render_garm_toml(
    *,
    listen_address: str,
    listen_port: int,
    db_path: str,
    jwt_secret: str,
) -> str:
    """Render GARM's TOML configuration file content.

    Args:
        listen_address: IP address for the GARM API server to bind on.
        listen_port: Port for the GARM API server.
        db_path: Filesystem path to the SQLite database file.
        jwt_secret: Secret string used to sign GARM JWT tokens.

    Returns:
        TOML-formatted string ready to be written to disk.
    """
    config: dict[str, typing.Any] = {
        "database": {
            "backend": "sqlite3",
            "sqlite3": {"db_file": db_path},
        },
        "apiserver": {
            "bind": listen_address,
            "port": listen_port,
            "use_tls": False,
        },
        "jwt_auth": {
            "secret": jwt_secret,
            "time_to_live": "8760h",
        },
        "metrics": {
            "disable_auth": True,
            "enable": True,
        },
        "provider": [
            {
                "name": "openstack",
                "provider_type": "external",
                "description": "OpenStack provider",
                "external": {
                    "config_file": "",
                    "provider_executable": OPENSTACK_PROVIDER_BINARY,
                    "environment_variables": [],
                },
            }
        ],
    }
    return tomli_w.dumps(config)


if __name__ == "__main__":
    ops.main(GarmCharm)  # type: ignore[name-defined]  # GarmCharm defined in Task 4
