#  Copyright 2025 Canonical Ltd.
#  See LICENSE file for licensing details.

"""Fixtures for charm tests."""

from pytest import Parser

CHARM_FILE_PARAM = "--charm-file"
PLANNER_IMAGE_PARAM = "--planner-image"
WEBHOOK_GATEWAY_IMAGE_PARAM = "--webhook-gateway-image"


def pytest_addoption(parser: Parser) -> None:
    """Parse additional pytest options.

    Args:
        parser: Pytest parser.
    """
    parser.addoption(
        CHARM_FILE_PARAM, action="append", help="Charm file to be deployed"
    )
    parser.addoption(
        PLANNER_IMAGE_PARAM, action="store", help="Planner app image to be deployed"
    )
    parser.addoption(
        WEBHOOK_GATEWAY_IMAGE_PARAM, action="store", help="Webhook gateway app image to be deployed"
    )
