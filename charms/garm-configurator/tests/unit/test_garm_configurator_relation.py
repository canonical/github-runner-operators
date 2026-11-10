# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the garm-configurator relation data model."""

import json

from garm_configurator_relation import ProviderConfig, decode_relation_value


def test_provider_config_defaults_are_empty_and_unpublished():
    """
    arrange: A provider config built from a unit databag that has not published anything.
    act: Inspect the defaults and the published flag.
    assert: Every field is empty and the config is not published, so a consumer skips the
        unit instead of failing validation while the relation is still being set up.
    """
    config = ProviderConfig()

    assert not config.is_published()
    assert not any(config.model_dump().values())


def test_provider_config_is_published_once_auth_url_is_set():
    """
    arrange: A provider config carrying an auth URL.
    act: Inspect the published flag.
    assert: The config counts as published, because the auth URL is the first field the
        configurator writes and the rest of the payload follows with it.
    """
    assert ProviderConfig(openstack_auth_url="https://ks.example.com:5000/v3").is_published()


def test_decode_relation_value_decodes_the_json_wire_format():
    """
    arrange: Values in the JSON form ``Relation.save`` writes.
    act: Decode them.
    assert: Strings and booleans come back as their Python values, so writer and reader share
        the same databag contract.
    """
    assert decode_relation_value(json.dumps("admin")) == "admin"
    assert decode_relation_value(json.dumps(True)) is True
    assert decode_relation_value(json.dumps(5)) == 5


def test_decode_relation_value_keeps_plain_strings_from_an_older_writer():
    """
    arrange: Legacy databag values that are not valid JSON, such as a bare URL.
    act: Decode them.
    assert: The raw string is returned rather than raising, so a mixed-version deployment
        stays readable during an upgrade.
    """
    assert decode_relation_value("https://ks.example.com:5000/v3") == (
        "https://ks.example.com:5000/v3"
    )
    assert decode_relation_value("secret://1234-5678") == "secret://1234-5678"
