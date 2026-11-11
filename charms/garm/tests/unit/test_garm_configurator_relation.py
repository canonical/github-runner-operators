# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the shared garm-configurator relation data model."""

import json

from garm_configurator_relation import decode_relation_value


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
