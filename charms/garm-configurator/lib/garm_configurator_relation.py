# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Pydantic models for the ``garm-configurator`` relation data contract.

The ``garm-configurator`` charm owns the relation contract and publishes one provider
configuration per unit with ``ops.Relation.save``. The models live with the charm so consumers
can share the same definitions and use ``ops.Relation.load`` instead of hand-writing databag
keys.
"""

import pydantic


@pydantic.dataclasses.dataclass
class ProviderConfig:
    """Provider and GitHub App credentials published by one ``garm-configurator`` unit.

    The field names are the relation databag keys, so they are the wire contract between the
    configurator and GARM. A unit publishes the provider payload only once its image and
    secrets are ready, so fields the selected provider does not use stay ``None``.

    Attributes:
        provider_type: Provider type, "openstack" or "lxd".
        openstack_auth_url: Keystone authentication URL.
        openstack_username: OpenStack username.
        openstack_password: Legacy plaintext password, or None when the secret URI is used.
        openstack_password_secret_uri: Juju secret URI holding the password.
        openstack_project_name: OpenStack project (tenant).
        openstack_user_domain_name: Domain of the user.
        openstack_project_domain_name: Domain of the project.
        openstack_region_name: OpenStack region.
        openstack_network: Network name or ID instances are attached to.
        lxd_api_url: LXD API URL.
        lxd_project_name: LXD project instances are created in.
        lxd_instance_type: LXD instance type, "container" or "virtual-machine".
        lxd_secure_boot: Whether LXD virtual machines use secure boot.
        lxd_client_certificate_secret_uri: Juju secret URI holding the client certificate.
        lxd_client_key_secret_uri: Juju secret URI holding the client key.
        lxd_server_certificate_secret_uri: Juju secret URI holding the server certificate.
        github_app_id: GitHub App ID.
        github_installation_id: GitHub App installation ID.
        github_private_key_secret_uri: Juju secret URI holding the GitHub App private key.
    """

    provider_type: str = "openstack"
    openstack_auth_url: str | None = None
    openstack_username: str | None = None
    openstack_password: str | None = None
    openstack_password_secret_uri: str | None = None
    openstack_project_name: str | None = None
    openstack_user_domain_name: str | None = None
    openstack_project_domain_name: str | None = None
    openstack_region_name: str | None = None
    openstack_network: str | None = None
    lxd_api_url: str | None = None
    lxd_project_name: str | None = None
    lxd_instance_type: str | None = None
    lxd_secure_boot: bool = False
    lxd_client_certificate_secret_uri: str | None = None
    lxd_client_key_secret_uri: str | None = None
    lxd_server_certificate_secret_uri: str | None = None
    github_app_id: int | None = None
    github_installation_id: int | None = None
    github_private_key_secret_uri: str | None = None
