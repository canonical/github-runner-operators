#!/usr/bin/env bash
# Generate the GARM Python API client from the GARM Swagger spec.
#
# Usage: bash charms/garm/scripts/generate_client.sh
#
# Requirements: Docker must be running. The generated output is written to
# charms/garm/src/garm_client/ and should be committed to the repository so
# that CI does not need Java or Docker for normal test/lint runs.
#
# To update to a newer GARM commit, change GARM_COMMIT below and re-run.

set -euo pipefail

GARM_COMMIT="47811d0046a9515085b85d88038f87ac68fd793c"
SWAGGER_URL="https://raw.githubusercontent.com/cloudbase/garm/${GARM_COMMIT}/webapp/swagger.yaml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
OUTPUT_DIR="${REPO_ROOT}/charms/garm/src"
PACKAGE_DIR="${OUTPUT_DIR}/garm_client"

echo "Downloading swagger.yaml from commit ${GARM_COMMIT}..."
curl -fsSL "${SWAGGER_URL}" -o /tmp/garm_swagger.yaml

echo "Cleaning previous output at ${PACKAGE_DIR}..."
rm -rf "${PACKAGE_DIR}"

echo "Running openapi-generator-cli via Docker..."
docker run --rm \
    -v /tmp/garm_swagger.yaml:/swagger.yaml:ro \
    -v "${OUTPUT_DIR}":/output \
    openapitools/openapi-generator-cli:v7.23.0 generate \
    --input-spec /swagger.yaml \
    --generator-name python \
    --output /output \
    --skip-validate-spec \
    --additional-properties=packageName=garm_client,generateSourceCodeOnly=true,library=urllib3

echo "Client generated at ${PACKAGE_DIR}"
