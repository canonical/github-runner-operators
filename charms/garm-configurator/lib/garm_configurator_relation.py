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
    """OpenStack provider credentials published by one ``garm-configurator`` unit.

    The field names are the relation databag keys, so they are the wire contract between the
    configurator and GARM. Only the auth URL is required: a unit publishes the rest of the
    provider payload alongside it, so the optional fields are ``None`` until then.

    Attributes:
        openstack_auth_url: Keystone authentication URL.
        openstack_username: OpenStack username.
        openstack_password: Legacy plaintext password, or None when the secret URI is used.
        openstack_password_secret_uri: Juju secret URI holding the password.
        openstack_project_name: OpenStack project (tenant).
        openstack_user_domain_name: Domain of the user.
        openstack_project_domain_name: Domain of the project.
        openstack_region_name: OpenStack region.
        openstack_network: Network name or ID instances are attached to.
    """

    openstack_auth_url: str
    openstack_username: str | None = None
    openstack_password: str | None = None
    openstack_password_secret_uri: str | None = None
    openstack_project_name: str | None = None
    openstack_user_domain_name: str | None = None
    openstack_project_domain_name: str | None = None
    openstack_region_name: str | None = None
    openstack_network: str | None = None

    def is_published(self) -> bool:
        """Whether the unit has published a usable provider configuration.

        Returns:
            True if the auth URL is set, the first field the configurator writes.
        """
        return bool(self.openstack_auth_url)
