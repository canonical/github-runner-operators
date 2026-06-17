# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
import json
import time
from typing import Any

import jubilant

# A throwaway RSA key used only to satisfy GARM's GitHub App credential parsing in
# integration tests. Not a real secret.
TEST_RSA_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIICXwIBAAKBgQC2tCW5B18y5VnqqokOeamJgasI3H1405WWv7FmWl31I1Cgabhi
MFcHdNECXFUC3wtqo/bXyCQbANRBkpZudJfSGos3+1iOJK1fd+MU8ntHVtgpvb5j
whdFSVJ9EL4/2u0K0S+fIyilD9q7K5mhk0MYLYWumPIRLkbtwr9a7LgY5wIDAQAB
AoGBAKIQGCoRjPNjmCfdT6fEaYtstt8sXiwQWu+WaHDnFdL9mWZBgOmwAXK+vyt9
5XafjMvyV2I+yTAewyjLM58U0xlslJu6Bk0Zw920sTmK9Qvvq/2mjsqw+PWr9rRx
qZFDCefAlB0Npo9tXHAf3ec5+vlm4QsEl6dty+Wx6aSHHMRpAkEA8e5IwkJZFcWO
aCc8Z+cnoidomlkvGlruncXMG1KhisQTleQVc1bM8tIZq2nNUG1zKJqHeCacQLiV
LKALnZDSCwJBAMFUIHd7ikYaAgTvrAKmzOZlMKVuGr2SHPODWoaWkEagEsrOw+H2
PYonSYkbzPyXH6iKUOhWH+ZA1r6K1lhdWhUCQQCquaTOsVN8cbVU+ps+F3l4jKbc
hSMgThsla3flsCIfcs7/b71Tb2Wh1XIX7Mnef95MQQBoYZbSdW+P1kFcJ96RAkEA
oSyuqI4BGDJkjpL1l3xSBJ5F8RUbDAI9SrKujNgHTinzoMrCOabdZUkdoEXiHo8r
IIq3qwrqKz7RCSecTSz+hQJBAJDKODanbnrPxNDgmIp52BMtiYI4vv7gKp/MSW0N
PG8an+PHNVGDEj1cOOwp/YNQieRp/WPH6bpBtwwe0r6pQZQ=
-----END RSA PRIVATE KEY-----"""


def poll_grafana_dashboard_templates(
    juju: jubilant.Juju, consumer_unit: str, attempts: int = 24, interval: int = 5
) -> dict[str, Any]:
    """Poll for dashboard templates via the grafana-dashboard consumer's relation data.

    Checks show-unit on the consumer side, where application-data contains
    the provider's data (including the dashboards key).
    Returns the templates dict if found, or an empty dict after all attempts are exhausted.
    """
    for _ in range(attempts):
        stdout = juju.cli("show-unit", consumer_unit, "--format=json")
        result = json.loads(stdout)
        for relation in result[consumer_unit]["relation-info"]:
            if relation["endpoint"] == "require-grafana-dashboard":
                dashboards_raw = relation["application-data"].get("dashboards")
                if dashboards_raw:
                    dashboards = json.loads(dashboards_raw)
                    templates = dashboards.get("templates", {})
                    if templates:
                        return templates
        time.sleep(interval)
    return {}
