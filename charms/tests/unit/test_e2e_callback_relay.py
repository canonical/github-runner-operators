# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Model-free tests for the E2E callback relay pre-install script.

The script only ever runs inside a runner VM on the tenant, so a syntax error or a
wrong redirect surfaces as a runner that never registers, half an hour into a live
run -- never as a red test.
"""

import re
import subprocess

from tests.e2e import conftest as fixtures

CALLBACK_HOST = "10.151.128.17"
RELAY = "10.151.122.71"


def test_relay_pre_install_script_redirects_garm_traffic_to_the_relay():
    """
    arrange: The CI host GARM's URLs point at, and the relay VM on the tenant.
    act: Render the runner VM's pre-install script.
    assert: The script is valid bash and DNATs the CI host's :80 and :443 to the relay's
        forwarded ports, so GARM's URLs and traefik's certificate work unchanged.
    """
    script = fixtures._relay_pre_install_script(callback_host=CALLBACK_HOST, relay=RELAY)

    subprocess.run(["bash", "-n"], input=script, text=True, check=True)
    assert re.search(
        r"daddr \$CALLBACK_HOST tcp dport 80 .*dnat to \$RELAY:\$RELAY_PORT\n", script
    )
    assert re.search(
        r"daddr \$CALLBACK_HOST tcp dport 443 .*dnat to \$RELAY:\$RELAY_TLS_PORT\n", script
    )
    assert f"CALLBACK_HOST='{CALLBACK_HOST}'" in script
    assert f"RELAY='{RELAY}'" in script
    assert f"RELAY_PORT={fixtures.E2E_RELAY_PORT}\n" in script
    assert f"RELAY_TLS_PORT={fixtures.E2E_RELAY_TLS_PORT}\n" in script


def test_relay_pre_install_script_carries_no_ssh_credentials():
    """
    arrange: The CI host and the relay addresses.
    act: Render the runner VM's pre-install script.
    assert: Nothing in it opens an SSH connection or writes a key, so the user data
        GARM hands every runner VM holds no credential worth tracing to its console.
    """
    script = fixtures._relay_pre_install_script(callback_host=CALLBACK_HOST, relay=RELAY)

    assert not re.search(r"\bssh\b|PRIVATE KEY|base64 -d", script)
