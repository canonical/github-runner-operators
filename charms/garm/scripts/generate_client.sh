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

# Patch the spec before generation. GARM renders the template `data` body (a Go []byte)
# as `type: array, items: {type: integer, format: uint8}`, but the actual JSON wire format
# is a base64 string. Rewrite the `data` property of the three template models to
# `type: string` so the generated client uses StrictStr instead of List[int].
# See https://github.com/cloudbase/garm/issues/796.
# Scoped to template models on purpose: other []byte fields (e.g. private_key_bytes) are
# still consumed as int-arrays elsewhere in the charm and must not be touched here.
echo 'Patching template data (uint8-array) properties to strings...'
python3 - /tmp/garm_swagger.yaml /tmp/garm_swagger.patched.yaml <<'PY'
import sys
import yaml

src, dst = sys.argv[1], sys.argv[2]
with open(src) as fh:
    spec = yaml.safe_load(fh)

TARGETS = ["Template", "CreateTemplateParams", "UpdateTemplateParams"]


def is_uint8_array(schema):
    if not isinstance(schema, dict) or schema.get("type") != "array":
        return False
    items = schema.get("items")
    return (
        isinstance(items, dict)
        and items.get("type") == "integer"
        and items.get("format") == "uint8"
    )


definitions = spec.get("definitions") or {}
patched = 0
for name in TARGETS:
    schema = (definitions.get(name) or {}).get("properties", {}).get("data")
    if not is_uint8_array(schema):
        raise SystemExit(
            f"{name}.data is not a uint8-array; spec may have changed, review the patch."
        )
    new_schema = {"type": "string"}
    if "x-go-name" in schema:
        new_schema["x-go-name"] = schema["x-go-name"]
    definitions[name]["properties"]["data"] = new_schema
    patched += 1

print(f"Patched the data field of {patched} template model(s) to strings.")

with open(dst, "w") as fh:
    yaml.safe_dump(spec, fh, sort_keys=True)
PY

echo "Cleaning previous output at ${PACKAGE_DIR}..."
rm -rf "${PACKAGE_DIR}"

echo "Running openapi-generator-cli via Docker..."
docker run --rm \
    -v /tmp/garm_swagger.patched.yaml:/swagger.yaml:ro \
    -v "${OUTPUT_DIR}":/output \
    openapitools/openapi-generator-cli:v7.23.0 generate \
    --input-spec /swagger.yaml \
    --generator-name python \
    --output /output \
    --skip-validate-spec \
    --additional-properties=packageName=garm_client,generateSourceCodeOnly=true,library=urllib3

echo "Client generated at ${PACKAGE_DIR}"
