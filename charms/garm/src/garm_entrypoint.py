#!/usr/bin/python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GARM 12-factor entrypoint.

Reads configuration from the environment variables injected by the charm and
writes GARM's file-based config.toml before exec'ing the GARM binary.
"""

import json
import logging
import os
import sys
import typing
from pathlib import Path
from typing import Final

import tomli_w
import yaml

logger = logging.getLogger(__name__)

GARM_CONFIG_PATH: Final[Path] = Path("/etc/garm/config.toml")
GARM_PROVIDER_CONFIG_DIR: Final[Path] = Path("/etc/garm")
OPENSTACK_PROVIDER_BINARY: Final[str] = "/usr/local/bin/garm-provider-openstack"
LXD_PROVIDER_BINARY: Final[str] = "/usr/local/bin/garm-provider-lxd"
DEFAULT_DB_PORT: Final[int] = 5432
DEFAULT_DB_NAME: Final[str] = "garm"
GARM_LISTEN_ADDRESS: Final[str] = "0.0.0.0"
GARM_PORT: Final[int] = 8080
PROVIDER_TYPE_OPENSTACK: Final[str] = "openstack"
PROVIDER_TYPE_LXD: Final[str] = "lxd"
SENSITIVE_ENV_VARS: Final[tuple[str, ...]] = (
    "POSTGRESQL_DB_USERNAME",
    "POSTGRESQL_DB_PASSWORD",
    "GARM_JWT_SECRET",
    "GARM_PASSPHRASE",
    "GARM_PROVIDERS_JSON",
)
OPENSTACK_PROVIDER_FIELDS: Final[tuple[str, ...]] = (
    "unit_name",
    "network",
    "auth_url",
    "username",
    "password",
    "project_name",
    "user_domain_name",
    "project_domain_name",
    "region_name",
)
LXD_PROVIDER_FIELDS: Final[tuple[str, ...]] = (
    "unit_name",
    "lxd_api_url",
    "lxd_project_name",
    "lxd_instance_type",
    "lxd_secure_boot",
    "lxd_client_certificate",
    "lxd_client_key",
    "lxd_server_certificate",
)
# The fields a provider config cannot be rendered without. The LXD server certificate is
# optional: when it is absent the provider falls back to the system trust store.
PROVIDER_REQUIRED_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    PROVIDER_TYPE_OPENSTACK: OPENSTACK_PROVIDER_FIELDS,
    PROVIDER_TYPE_LXD: (
        "unit_name",
        "lxd_api_url",
        "lxd_client_certificate",
        "lxd_client_key",
    ),
}
# The image remotes GARM's LXD provider gets by default. "ubuntu" covers the release
# catalogue the configurator's image option refers to (for example ubuntu:24.04).
DEFAULT_LXD_IMAGE_REMOTES: Final[dict[str, dict[str, typing.Any]]] = {
    "ubuntu": {
        "addr": "https://cloud-images.ubuntu.com/releases",
        "public": True,
        "protocol": "simplestreams",
        "skip_verify": False,
    }
}


class GarmEntrypointError(Exception):
    """Base exception for expected entrypoint configuration failures."""


class MissingEnvironmentError(GarmEntrypointError):
    """Raised when a required environment variable is missing."""


class InvalidConfigurationError(GarmEntrypointError):
    """Raised when an environment value cannot configure GARM."""


def _read_env_vars() -> dict[str, str]:
    """Read and validate the environment variables required by GARM.

    Returns:
        A dictionary of environment variable name to value.

    Raises:
        MissingEnvironmentError: If any required variable is missing.
    """
    required = (
        "POSTGRESQL_DB_HOSTNAME",
        "POSTGRESQL_DB_USERNAME",
        "POSTGRESQL_DB_PASSWORD",
        "GARM_JWT_SECRET",
        "GARM_PASSPHRASE",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise MissingEnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    return {
        name: os.environ.get(name, "")
        for name in (
            *required,
            "POSTGRESQL_DB_PORT",
            "POSTGRESQL_DB_NAME",
            "APP_BASE_URL",
            "GARM_PROVIDERS_JSON",
            "http_proxy",
            "https_proxy",
            "no_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "NO_PROXY",
        )
        if os.environ.get(name) is not None
    }


def _build_config(env: dict[str, str]) -> dict[str, typing.Any]:
    """Build a GARM config dictionary from environment variables.

    Args:
        env: Dictionary of validated environment variables.

    Returns:
        Configuration dictionary suitable for tomli_w.
    """
    try:
        db_port = int(env.get("POSTGRESQL_DB_PORT", DEFAULT_DB_PORT))
    except ValueError as exc:
        raise InvalidConfigurationError("POSTGRESQL_DB_PORT must be an integer") from exc
    if not 1 <= db_port <= 65535:
        raise InvalidConfigurationError("POSTGRESQL_DB_PORT must be between 1 and 65535")
    db_name = env.get("POSTGRESQL_DB_NAME", DEFAULT_DB_NAME)
    base_url = env.get("APP_BASE_URL", "").rstrip("/")

    config: dict[str, typing.Any] = {
        "database": {
            "backend": "postgresql",
            "passphrase": env["GARM_PASSPHRASE"],
            "postgresql": {
                "hostname": env["POSTGRESQL_DB_HOSTNAME"],
                "port": db_port,
                "username": env["POSTGRESQL_DB_USERNAME"],
                "password": env["POSTGRESQL_DB_PASSWORD"],
                "database": db_name,
                "sslmode": "prefer",
            },
        },
        "apiserver": {
            "bind": GARM_LISTEN_ADDRESS,
            "port": GARM_PORT,
            "use_tls": False,
        },
        "jwt_auth": {
            "secret": env["GARM_JWT_SECRET"],
            "time_to_live": "8760h",
        },
        "metrics": {
            "disable_auth": True,
            "enable": True,
        },
        "metadata_url": f"{base_url}/api/v1/metadata" if base_url else "",
        "callback_url": f"{base_url}/api/v1/callbacks" if base_url else "",
    }

    config["provider"], _ = _build_provider_files(env)

    return config


def _build_provider_files(
    env: dict[str, str] | None = None,
) -> tuple[list[dict[str, typing.Any]], dict[str, str]]:
    """Build GARM provider entries and their OpenStack config files."""
    env = dict(os.environ) if env is None else env
    providers = _parse_providers(env)
    proxy_vars = sorted(
        name
        for name in (
            "http_proxy",
            "https_proxy",
            "no_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "NO_PROXY",
        )
        if env.get(name)
    )
    entries: list[dict[str, typing.Any]] = []
    files: dict[str, str] = {}
    for provider in providers:
        entry, provider_files = _build_provider(provider, proxy_vars)
        entries.append(entry)
        files.update(provider_files)
    return entries, files


def _parse_providers(env: dict[str, str]) -> list[typing.Any]:
    """Parse GARM_PROVIDERS_JSON into a list of provider objects.

    Args:
        env: Dictionary of environment variables.

    Returns:
        The provider objects, or an empty list when unset.

    Raises:
        InvalidConfigurationError: If the value is not valid JSON or not a list.
    """
    providers_json = env.get("GARM_PROVIDERS_JSON", "")
    if not providers_json:
        return []
    try:
        providers = json.loads(providers_json)
    except json.JSONDecodeError as exc:
        raise InvalidConfigurationError("GARM_PROVIDERS_JSON must contain valid JSON") from exc
    if not isinstance(providers, list):
        raise InvalidConfigurationError("GARM_PROVIDERS_JSON must contain a JSON list")
    return providers


def _build_provider(
    provider: typing.Any, proxy_vars: list[str]
) -> tuple[dict[str, typing.Any], dict[str, str]]:
    """Build one external provider entry plus the files its executable reads.

    Args:
        provider: One provider object from GARM_PROVIDERS_JSON (untrusted input).
        proxy_vars: Proxy variable names to forward to the provider executable.

    Returns:
        The provider config entry and its config files, keyed by path.

    Raises:
        InvalidConfigurationError: If the provider object is not a JSON object, its
            provider type or unit name is invalid, or required fields are missing.
    """
    if not isinstance(provider, dict):
        raise InvalidConfigurationError("Each GARM provider must be a JSON object")
    unit_name = provider.get("unit_name")
    if not isinstance(unit_name, str) or not unit_name or Path(unit_name).name != unit_name:
        raise InvalidConfigurationError(f"Invalid provider unit name: {unit_name!r}")
    provider_type = str(provider.get("provider_type") or PROVIDER_TYPE_OPENSTACK)
    if provider_type not in PROVIDER_REQUIRED_FIELDS:
        raise InvalidConfigurationError(f"Invalid provider type: {provider_type!r}")
    missing = [name for name in PROVIDER_REQUIRED_FIELDS[provider_type] if name not in provider]
    if missing:
        raise InvalidConfigurationError(
            f"GARM provider is missing required fields: {', '.join(missing)}"
        )
    if provider_type == PROVIDER_TYPE_LXD:
        return _build_lxd_provider(provider, unit_name, proxy_vars)
    return _build_openstack_provider(provider, unit_name, proxy_vars)


def _build_openstack_provider(
    provider: dict[str, typing.Any], unit_name: str, proxy_vars: list[str]
) -> tuple[dict[str, typing.Any], dict[str, str]]:
    """Build the OpenStack provider entry, its provider TOML, and its clouds YAML."""
    provider_path = GARM_PROVIDER_CONFIG_DIR / f"provider-{unit_name}.toml"
    clouds_path = GARM_PROVIDER_CONFIG_DIR / f"clouds-{unit_name}.yaml"
    entry = {
        "name": unit_name,
        "provider_type": "external",
        "description": f"OpenStack provider ({unit_name})",
        "external": {
            "config_file": str(provider_path),
            "provider_executable": OPENSTACK_PROVIDER_BINARY,
            **({"environment_variables": proxy_vars} if proxy_vars else {}),
        },
    }
    files = {
        str(provider_path): tomli_w.dumps(
            {
                "cloud": unit_name,
                "network_id": provider["network"],
                "credentials": {"clouds": str(clouds_path)},
                "use_config_drive": True,
            }
        ),
        str(clouds_path): yaml.safe_dump(
            {
                "clouds": {
                    unit_name: {
                        "auth": {
                            key: provider[key]
                            for key in (
                                "auth_url",
                                "username",
                                "password",
                                "project_name",
                                "user_domain_name",
                                "project_domain_name",
                            )
                        },
                        "region_name": provider["region_name"],
                    }
                }
            },
            sort_keys=False,
        ),
    }
    return entry, files


def _build_lxd_provider(
    provider: dict[str, typing.Any], unit_name: str, proxy_vars: list[str]
) -> tuple[dict[str, typing.Any], dict[str, str]]:
    """Build the LXD provider entry, its provider TOML, and its certificate files."""
    provider_path = GARM_PROVIDER_CONFIG_DIR / f"provider-{unit_name}.toml"
    client_certificate_path = GARM_PROVIDER_CONFIG_DIR / f"provider-{unit_name}-client.crt"
    client_key_path = GARM_PROVIDER_CONFIG_DIR / f"provider-{unit_name}-client.key"
    server_certificate_path = GARM_PROVIDER_CONFIG_DIR / f"provider-{unit_name}-server.crt"
    entry = {
        "name": unit_name,
        "provider_type": "external",
        "description": f"LXD provider ({unit_name})",
        "external": {
            "config_file": str(provider_path),
            "provider_executable": LXD_PROVIDER_BINARY,
            **({"environment_variables": proxy_vars} if proxy_vars else {}),
        },
    }
    config: dict[str, typing.Any] = {
        "unix_socket_path": "",
        "include_default_profile": False,
        "instance_type": provider.get("lxd_instance_type") or "virtual-machine",
        "secure_boot": bool(provider.get("lxd_secure_boot", False)),
        "project_name": provider.get("lxd_project_name") or "default",
        "url": provider["lxd_api_url"],
        "client_certificate": str(client_certificate_path),
        "client_key": str(client_key_path),
    }
    files = {
        str(client_certificate_path): provider["lxd_client_certificate"],
        str(client_key_path): provider["lxd_client_key"],
    }
    server_certificate = provider.get("lxd_server_certificate")
    if server_certificate:
        config["tls_server_certificate"] = str(server_certificate_path)
        files[str(server_certificate_path)] = server_certificate
    # Tables must come last so tomli_w keeps the scalar keys above them at the top
    # level rather than nesting them under [image_remotes.ubuntu].
    config["image_remotes"] = DEFAULT_LXD_IMAGE_REMOTES
    files[str(provider_path)] = tomli_w.dumps(config)
    return entry, files


def render_garm_config(env: dict[str, str]) -> str:
    """Render GARM config.toml content from environment variables.

    Args:
        env: Dictionary of validated environment variables.

    Returns:
        TOML-formatted configuration string.
    """
    return tomli_w.dumps(_build_config(env))


def write_config(content: str) -> None:
    """Write the rendered config to /etc/garm/config.toml.

    Args:
        content: The TOML configuration string.
    """
    GARM_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    GARM_CONFIG_PATH.write_text(content, encoding="utf-8")
    os.chmod(GARM_CONFIG_PATH, 0o600)
    logger.info("Wrote GARM configuration to %s", GARM_CONFIG_PATH)


def _scrub_sensitive_env_vars() -> None:
    """Remove sensitive values from the process environment before exec."""
    for name in SENSITIVE_ENV_VARS:
        os.environ.pop(name, None)


def main() -> None:
    """Render GARM config and exec the GARM binary."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        env = _read_env_vars()
        logger.info("Starting GARM configuration preparation: env_keys=%s", sorted(env))
        config = render_garm_config(env)
        _, provider_files = _build_provider_files(env)
        write_config(config)
        GARM_PROVIDER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        expected_paths = set(provider_files)
        for path in GARM_PROVIDER_CONFIG_DIR.iterdir():
            name = path.name
            if not name.startswith(("provider-", "clouds-")) or not name.endswith(
                (".toml", ".yaml", ".crt", ".key")
            ):
                continue
            if str(path) not in expected_paths:
                path.unlink()
        for path, content in provider_files.items():
            provider_path = Path(path)
            provider_path.parent.mkdir(parents=True, exist_ok=True)
            provider_path.write_text(content, encoding="utf-8")
            os.chmod(provider_path, 0o600)
        _scrub_sensitive_env_vars()
        logger.info(
            "Prepared GARM configuration: provider_count=%d config_path=%s",
            len(_parse_providers(env)),
            GARM_CONFIG_PATH,
        )
        logger.info(
            "Starting GARM process: command=/usr/local/bin/garm config_path=%s",
            GARM_CONFIG_PATH,
        )
        # GARM's CLI moved to cobra (upstream PR #782), which requires GNU-style
        # double-dash long flags; "-config" now silently misparses instead of
        # being read as an alias for "--config".
        os.execvp("/usr/local/bin/garm", ["garm", "--config", str(GARM_CONFIG_PATH)])
    except (GarmEntrypointError, OSError):
        logger.exception("Failed to prepare GARM configuration")
        sys.exit(1)


if __name__ == "__main__":
    main()
