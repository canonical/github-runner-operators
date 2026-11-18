# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for charm state image resolution."""

from types import SimpleNamespace

import pytest

from charm_state import CharmState


def _image_relation(image_id: str | None = None):
    """Build the smallest relation-shaped object needed by image resolution."""
    unit = "image-builder/0"
    return SimpleNamespace(
        units=(unit,),
        data={unit: {"id": image_id} if image_id is not None else {}},
    )


@pytest.mark.parametrize(
    ("image_configuration", "image_relation", "expected_image", "overrides_builder"),
    [
        pytest.param(None, None, None, False, id="no-image-source"),
        pytest.param("configured-image", None, "configured-image", False, id="configured-only"),
        pytest.param(
            None, _image_relation("related-image"), "related-image", False, id="relation-only"
        ),
        pytest.param(
            "configured-image",
            _image_relation("related-image"),
            "configured-image",
            True,
            id="configured-image-takes-precedence",
        ),
        pytest.param(
            "configured-image",
            _image_relation(),
            "configured-image",
            True,
            id="configured-image-does-not-wait-for-relation-data",
        ),
    ],
)
def test_image_properties_are_derived_from_source_state(
    image_configuration, image_relation, expected_image, overrides_builder
):
    """Resolve image state from configuration and the image-builder relation."""
    state = CharmState(
        provider_config=None,
        github_app_config=None,
        scaleset_config=None,
        runner_config=None,
        image_relation=image_relation,
        image_configuration=image_configuration,
    )

    assert state.image == expected_image
    assert state.image_overrides_builder is overrides_builder
