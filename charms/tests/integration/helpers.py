# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
import json
import time
from typing import Any

import jubilant


def poll_grafana_dashboard_templates(
    juju: jubilant.Juju, unit: str, attempts: int = 24, interval: int = 5
) -> dict[str, Any]:
    """Poll for dashboard templates in the grafana-dashboard relation data.

    Returns the templates dict if found, or an empty dict after all attempts are exhausted.
    """
    for _ in range(attempts):
        stdout = juju.cli("show-unit", unit, "--format=json")
        result = json.loads(stdout)
        for relation in result[unit]["relation-info"]:
            if relation["endpoint"] == "grafana-dashboard":
                dashboards_raw = relation["application-data"].get("dashboards")
                if dashboards_raw:
                    dashboards = json.loads(dashboards_raw)
                    templates = dashboards.get("templates", {})
                    if templates:
                        return templates
        time.sleep(interval)
    return {}
