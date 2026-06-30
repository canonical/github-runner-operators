# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm state parsing for the GARM charm.

Consolidates the desired GARM state derived from charm relations into a single ``CharmState``
value (built via ``CharmState.from_charm``), keeping ``charm.py`` free of relation-parsing detail.
"""

import dataclasses
import logging
import typing

import ops

from entity_reconciler import EntitySpec

logger = logging.getLogger(__name__)

GARM_CONFIGURATOR_RELATION_NAME: typing.Final[str] = "garm-configurator"


def _credential_name(app_id: int, installation_id: int) -> str:
    """Return the GARM credential name for a GitHub App installation.

    The org/repo entity reconciler binds entities to credentials by this name, so both the
    credential and entity builders must derive it identically.
    """
    return f"app-{app_id}-{installation_id}"


def _get_desired_entities(charm: ops.CharmBase) -> list[EntitySpec]:
    """Build the desired GARM org/repo entities from configurator relation data.

    Each entity is bound to the GitHub App credential the github reconciler creates for the same
    configurator unit (``app-<app_id>-<installation_id>``). A unit naming an org or repo but
    lacking the App ids is skipped — its credential name cannot be derived.

    Args:
        charm: The charm instance.

    Returns:
        The full desired set of entity specs.
    """
    entities: dict[tuple[str, str], EntitySpec] = {}
    # Iterate relations and units in a stable order so the "keep the first" tie-break below is
    # deterministic: relation.units is an unordered set, so without sorting two units naming the
    # same entity with different credentials would flip-flop across reconciles.
    relations = sorted(
        charm.model.relations.get(GARM_CONFIGURATOR_RELATION_NAME, []), key=lambda r: r.id
    )
    for relation in relations:
        for unit in sorted(relation.units, key=lambda unit: unit.name):
            data = relation.data[unit]
            org = data.get("org", "")
            repo = data.get("repo", "")
            if org:
                entity_type, entity_name = "organization", org
            elif repo:
                entity_type, entity_name = "repository", repo
            else:
                continue

            app_id_raw = data.get("github_app_id", "")
            installation_id_raw = data.get("github_installation_id", "")
            # Skip quietly while the App ids are merely absent (the configurator publishes the
            # entity name before them during bring-up); warn only on malformed values.
            if not (app_id_raw and installation_id_raw):
                continue
            try:
                app_id = int(app_id_raw)
                installation_id = int(installation_id_raw)
            except ValueError:
                logger.warning(
                    "Skipping entity %s from %s: non-numeric app/installation id "
                    "(app_id=%r, installation_id=%r)",
                    entity_name,
                    unit.name,
                    app_id_raw,
                    installation_id_raw,
                )
                continue

            # Dedupe by (type, name) so an org and a repo sharing a raw name don't collide. Keep
            # the first spec seen (iteration is ordered above) and warn if a later one derives a
            # different credential.
            key = (entity_type, entity_name)
            credentials_name = _credential_name(app_id, installation_id)
            existing = entities.get(key)
            if existing is not None:
                if existing.credentials_name != credentials_name:
                    logger.warning(
                        "Conflicting credential for %s '%s' (%s vs %s); keeping the first",
                        entity_type,
                        entity_name,
                        existing.credentials_name,
                        credentials_name,
                    )
                continue
            entities[key] = EntitySpec(
                entity_type=entity_type,
                entity_name=entity_name,
                credentials_name=credentials_name,
            )
    return list(entities.values())


@dataclasses.dataclass(frozen=True)
class CharmState:
    """Consolidated desired state for the GARM charm.

    Attributes:
        desired_entities: GARM org/repo entities derived from the garm-configurator relation.
    """

    desired_entities: list[EntitySpec]

    @classmethod
    def from_charm(cls, charm: ops.CharmBase) -> "CharmState":
        """Build CharmState from the current charm instance.

        Args:
            charm: The charm instance.

        Returns:
            Current CharmState.
        """
        return cls(desired_entities=_get_desired_entities(charm))
