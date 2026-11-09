# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Pydantic models for the ``garm-configurator`` relation data contract.

The ``garm-configurator`` charm publishes one provider configuration per unit on the
``garm-configurator`` relation, and the ``garm`` charm consumes it. Keeping the models in one
shared module means the writer and the reader cannot drift: both build the same model and use
``ops.Relation.save`` / ``ops.Relation.load`` rather than hand-writing databag keys.
"""

import json
import typing

import pydantic


class ProviderConfig(pydantic.BaseModel):
    """OpenStack provider credentials published by one ``garm-configurator`` unit.

    The field names are the relation databag keys, so they are the wire contract between the
    configurator and GARM. Every field defaults to an empty string because a unit publishes
    the provider payload only once its image and secrets are ready: until then it is absent
    from the databag rather than invalid.

    Attributes:
        openstack_auth_url: Keystone authentication URL.
        openstack_username: OpenStack username.
        openstack_password: Legacy plaintext password, or "" when the secret URI is used.
        openstack_password_secret_uri: Juju secret URI holding the password.
        openstack_project_name: OpenStack project (tenant).
        openstack_user_domain_name: Domain of the user.
        openstack_project_domain_name: Domain of the project.
        openstack_region_name: OpenStack region.
        openstack_network: Network name or ID instances are attached to.
    """

    openstack_auth_url: str = ""
    openstack_username: str = ""
    openstack_password: str = ""
    openstack_password_secret_uri: str = ""
    openstack_project_name: str = ""
    openstack_user_domain_name: str = ""
    openstack_project_domain_name: str = ""
    openstack_region_name: str = ""
    openstack_network: str = ""

    def is_published(self) -> bool:
        """Whether the unit has published a usable provider configuration.

        Returns:
            True if the auth URL is set, the first field the configurator writes.
        """
        return bool(self.openstack_auth_url)


def decode_relation_value(value: str) -> typing.Any:
    """Decode one relation databag value written by ``ops.Relation.save``.

    ``Relation.load`` decodes JSON by default, but a relation can span an upgrade where the
    remote unit still writes plain strings, or where a legacy field holds a secret URI that is
    not valid JSON. Falling back to the raw string keeps a mixed-version deployment readable.

    Args:
        value: The raw databag value.

    Returns:
        The decoded JSON value, or the raw string when it is not JSON.
    """
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value
