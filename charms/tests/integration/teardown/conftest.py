"""Fixtures for the ProdStack-backed GARM teardown integration suite."""

# Import fixture objects into this conftest so pytest registers the E2E fixture graph
# for this suite. The normal integration suite does not provide real OpenStack values;
# the test module skips there when OS_AUTH_URL is absent.
from tests.e2e.conftest import (  # noqa: F401
    deploy_e2e_scaleset_fixture,
    deploy_image_builder_stub_fixture,
    deploy_traefik_fixture,
    garm_with_ingress,
    integrate_garm_ingress_fixture,
    openstack_credentials_fixture,
)
from tests.integration.conftest import (  # noqa: F401
    deploy_garm_app_no_integration_fixture,
    deploy_postgresql_server_fixture,
    garm_app_image_fixture,
    garm_charm_file_fixture,
    garm_configurator_charm_file_fixture,
    integrate_garm_with_postgresql_fixture,
    juju,
)
