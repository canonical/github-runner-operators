# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""OWASP-compliant security event logger for the garm charm.

Single source of truth for the ``appid`` used in every security event and in the
Sigma detection rules under ``docs/security/sigma/garm/`` (logsource.product).
Import ``owasp_log`` wherever a security event occurs; never re-instantiate it.
"""

from owasp_logger import OWASPLogger

APPID = "canonical.garm"

owasp_log = OWASPLogger(appid=APPID)
