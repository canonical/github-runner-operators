#!/usr/bin/env bash
# Throwaway harness validating the garm charm's s390x support on s390x.
#
# Runs GARM at the commit garm-rockcraft.yaml pins, with garm-provider-lxd, on
# this s390x runner. The charm's own code then points GARM at the charm's
# default runner tools URL and publishes the garm-agent binaries built by the
# rock's own build script. GARM boots one s390x LXD container in agent mode
# that registers as a runner of this repo, and the workflow routes a job to it.
#
# The charm runs the OpenStack provider; this harness uses LXD instead, since
# there is no s390x OpenStack to target from CI.
#
# Usage: garm-s390x.sh setup|diagnostics|teardown
#
# Required env: PROVIDER_LXD_SHA, RUNNER_LABEL, GITHUB_REPOSITORY, GITHUB_TOKEN,
# E2E_GITHUB_APP_ID, E2E_GITHUB_APP_INSTALLATION_ID, E2E_GITHUB_APP_PRIVATE_KEY.

set -euo pipefail
# The App key, the DB passphrase and the admin password all land in files here.
umask 077

WORK="${RUNNER_TEMP:-/tmp}/garm-charm"
GARM_PORT=9997
GARM_UNIT=garm-charm
VENV="$WORK/venv"
# What the rock's garm-agent part installs, laid out as in the workload container.
ROCK_ROOT="$WORK/rock"
IMAGE="ubuntu:24.04"

main() {
  case "${1:-}" in
    setup) setup ;;
    diagnostics) diagnostics ;;
    teardown) teardown ;;
    *) echo "usage: $0 setup|diagnostics|teardown" >&2; exit 2 ;;
  esac
}

setup() {
  mkdir -p "$WORK"
  sudo apt-get -qq update
  sudo apt-get -qq install -y build-essential file jq netcat-openbsd python3-venv

  setup_python
  GARM_SHA="$(rock_part_field garm source-commit)"
  TOOLS_METADATA_URL="$(charm_tools_metadata_url)"
  build_garm
  build_provider
  build_agent
  setup_lxd
  start_garm
  # Before GARM boots anything: a runner that never registers says nothing
  # about the PR if the container could not reach GARM or GitHub to begin with.
  probe_container_network
  configure_garm
}

build_garm() {
  echo "::group::Build GARM at ${GARM_SHA}"
  fetch_at cloudbase/garm "$GARM_SHA" "$WORK/garm"
  make -C "$WORK/garm" build
  sudo install -m 0755 "$WORK/garm/bin/garm" "$WORK/garm/bin/garm-cli" /usr/local/bin/
  echo "::endgroup::"
}

# The charm's GARM code needs only its own pinned runtime dependencies, not Juju.
setup_python() {
  echo "::group::Set up Python for the charm code"
  python3 -m venv "$VENV"
  grep -E '^(ops|urllib3|python-dateutil|pydantic|typing-extensions|owasp-logger|PyYAML)==' \
    charms/garm/requirements.txt > "$WORK/requirements.txt"
  "$VENV/bin/pip" install -q -r "$WORK/requirements.txt"
  echo "::endgroup::"
}

rock_part_field() {
  "$VENV/bin/python" -I -c 'import sys, yaml
print(yaml.safe_load(open("garm-rockcraft.yaml"))["parts"][sys.argv[1]][sys.argv[2]])' "$1" "$2"
}

charm_tools_metadata_url() {
  "$VENV/bin/python" -I -c 'import yaml
print(yaml.safe_load(open("charms/garm/charmcraft.yaml"))["config"]["options"]["runner-tools-metadata-url"]["default"])'
}

build_provider() {
  echo "::group::Build garm-provider-lxd at ${PROVIDER_LXD_SHA}"
  fetch_at cloudbase/garm-provider-lxd "$PROVIDER_LXD_SHA" "$WORK/garm-provider-lxd"
  (cd "$WORK/garm-provider-lxd" && go build -o "$WORK/garm-provider-lxd.bin" .)
  echo "::endgroup::"
}

# Runs the rock's own garm-agent build script, so the binaries and manifest are
# the ones the rock ships, cross-compiled for every architecture it lists.
build_agent() {
  local tag
  tag="$(rock_part_field garm-agent source-tag)"
  echo "::group::Build garm-agent ${tag} with the rock's build script"
  git clone -q --depth 1 --branch "$tag" https://github.com/cloudbase/garm-agent "$WORK/garm-agent"
  rock_part_field garm-agent override-build > "$WORK/build-agent.sh"
  mkdir -p "$ROCK_ROOT"
  (
    export CRAFT_PART_SRC="$WORK/garm-agent" CRAFT_PART_INSTALL="$ROCK_ROOT"
    export GOTOOLCHAIN=local CGO_ENABLED=0
    bash -euo pipefail "$WORK/build-agent.sh"
  )
  cat "$ROCK_ROOT/opt/garm-agent/manifest.txt"
  file "$ROCK_ROOT/opt/garm-agent/linux/s390x/garm-agent"
  echo "::endgroup::"
}

fetch_at() {
  local repo="$1" sha="$2" dir="$3"
  git init -q "$dir"
  git -C "$dir" fetch -q --depth 1 "https://github.com/${repo}" "$sha"
  git -C "$dir" checkout -q FETCH_HEAD
}

setup_lxd() {
  echo "::group::Set up LXD"
  if ! snap list lxd >/dev/null 2>&1; then
    sudo snap install lxd
  fi
  sudo lxd waitready
  sudo lxd init --auto

  # Containers are NATed, not encapsulated, so the bridge can match the host.
  # OpenStack networks commonly sit below 1500, and lxdbr0's 1500 default then
  # stalls TLS downloads while small requests still get through.
  local iface mtu
  iface="$(ip route show default | awk '{print $5; exit}')"
  mtu="$(cat "/sys/class/net/${iface}/mtu")"
  sudo lxc network set lxdbr0 bridge.mtu "$mtu"
  echo "lxdbr0 MTU set to ${mtu} (from ${iface})"

  BRIDGE_IP="$(sudo lxc network get lxdbr0 ipv4.address | cut -d/ -f1)"
  echo "BRIDGE_IP=${BRIDGE_IP}" >> "${GITHUB_ENV:-/dev/null}"
  echo "::endgroup::"
}

start_garm() {
  echo "::group::Start GARM"
  cat > "$WORK/garm-provider-lxd.toml" <<EOF
unix_socket_path = "/var/snap/lxd/common/lxd/unix.socket"
include_default_profile = false
instance_type = "container"
secure_boot = false
project_name = "default"
[image_remotes]
  [image_remotes.ubuntu]
    addr = "https://cloud-images.ubuntu.com/releases"
    public = true
    protocol = "simplestreams"
    skip_verify = false
EOF

  cat > "$WORK/config.toml" <<EOF
[default]
enable_webhook_management = false

[logging]
log_format = "text"
log_level = "debug"

[jwt_auth]
secret = "$(random_secret)"
time_to_live = "8760h"

[apiserver]
bind = "0.0.0.0"
port = ${GARM_PORT}
use_tls = false

[database]
backend = "sqlite3"
passphrase = "$(random_secret)"
[database.sqlite3]
  db_file = "${WORK}/garm.db"

[[provider]]
name = "lxd_local"
provider_type = "external"
description = "Local LXD"
  [provider.external]
    provider_executable = "${WORK}/garm-provider-lxd.bin"
    config_file = "${WORK}/garm-provider-lxd.toml"
EOF
  chmod 600 "$WORK/config.toml"

  # Root, so GARM and the provider it executes can reach the LXD socket
  # without depending on group membership this shell does not have yet.
  sudo systemd-run --unit "$GARM_UNIT" --collect \
    /usr/local/bin/garm --config "$WORK/config.toml"

  local deadline=$((SECONDS + 60))
  until nc -z 127.0.0.1 "$GARM_PORT"; do
    if (( SECONDS > deadline )); then
      echo "::error::GARM did not open port ${GARM_PORT} within 60s"
      return 1
    fi
    sleep 1
  done
  echo "::endgroup::"
}

probe_container_network() {
  echo "::group::Probe container network"
  local release_assets
  release_assets="$(curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN}" "$TOOLS_METADATA_URL" \
    | jq -r '[.[] | select(.prerelease | not)][0].assets[] | select(.name | test("linux-s390x")) | .browser_download_url')"
  sudo lxc launch "$IMAGE" garm-probe
  local url
  for url in "http://${BRIDGE_IP}:${GARM_PORT}/api/v1/metadata/" https://api.github.com "$release_assets"; do
    # The metadata endpoint answers 401 without a runner token, which still
    # proves the route; only a transport failure fails this check. The asset
    # redirects to a separate download host, so follow it, but fetch one byte.
    if ! retry 12 5 sudo lxc exec garm-probe -- \
        curl -sS -L -r 0-0 -o /dev/null --max-time 30 -w "%{http_code} ${url%%\?*}\n" "$url"; then
      echo "::error::The container cannot reach ${url%%\?*}. Check egress/proxy rules and MTU on this runner."
      return 1
    fi
  done
  sudo lxc delete --force garm-probe
  echo "::endgroup::"
}

configure_garm() {
  echo "::group::Configure GARM"
  local password private_key repo_id scaleset_id
  password="$(random_secret)"
  echo "::add-mask::${password}"
  printf '%s' "$password" > "$WORK/admin-password"
  garm-cli init --name local --url "http://${BRIDGE_IP}:${GARM_PORT}" \
    --username admin --email admin@example.invalid --full-name admin \
    --password-file "$WORK/admin-password"
  # The agent dials back over plain ws, as the charm allows when GARM is not on https.
  garm-cli controller update --allow-insecure-agent

  # The behaviour under test, through the charm's own code: the runner tools URL
  # on the endpoint, and the rock's garm-agent binaries in GARM's tool store.
  "$VENV/bin/python" -I .github/garm-charm-s390x/charm_steps.py \
    "http://127.0.0.1:${GARM_PORT}/api/v1" "$WORK/admin-password" "$ROCK_ROOT"
  garm-cli github endpoint show github.com
  garm-cli controller show

  private_key="$WORK/app.pem"
  # Same normalisation garm_e2e.yaml applies: the secret may be PEM or base64.
  case "$E2E_GITHUB_APP_PRIVATE_KEY" in
    *-----BEGIN*) printf '%s\n' "$E2E_GITHUB_APP_PRIVATE_KEY" > "$private_key" ;;
    *) printf '%s' "$E2E_GITHUB_APP_PRIVATE_KEY" | base64 -d > "$private_key" ;;
  esac
  chmod 600 "$private_key"
  garm-cli github credentials add --name e2e-app --description "garm charm s390x test" \
    --endpoint github.com --auth-type app \
    --app-id "$E2E_GITHUB_APP_ID" --app-installation-id "$E2E_GITHUB_APP_INSTALLATION_ID" \
    --private-key-path "$private_key"
  rm -f "$private_key"

  repo_id="$(garm-cli repo add --owner "${GITHUB_REPOSITORY%%/*}" --name "${GITHUB_REPOSITORY#*/}" \
    --credentials e2e-app --random-webhook-secret --agent-mode --format json | jq -r .id)"

  wait_for_s390x_tools

  # A scale set learns of jobs over its message session with GitHub, so no
  # webhook or idle runner is needed: GARM boots a runner when the job is queued.
  # GitHub routes jobs to a scale set by its name, which is why it is the label.
  # Canonical's s390x runner, unlike GitHub's builds, is not self-contained and
  # needs the system .NET 8 runtime, as Canonical's runner images install it.
  scaleset_id="$(garm-cli scaleset add --repo "$repo_id" --name "$RUNNER_LABEL" \
    --provider-name lxd_local --image "$IMAGE" --flavor default \
    --os-type linux --os-arch s390x --min-idle-runners 0 --max-runners 1 --enabled \
    --extra-specs '{"extra_packages": ["dotnet-runtime-8.0"]}' \
    --format json | jq -r .id)"
  echo "SCALESET_ID=${scaleset_id}" >> "${GITHUB_ENV:-/dev/null}"
  garm-cli scaleset show "$scaleset_id"
  echo "::endgroup::"
}

# Any runner GARM starts before it has s390x tools fails in the provider, so the
# scale set waits for them. Main fetches the metadata URL with the endpoint's
# credentials, so this should pass on GARM's first sync rather than after the
# unauthenticated 403s an earlier run hit.
wait_for_s390x_tools() {
  local deadline=$((SECONDS + 900))
  until sudo journalctl -u "$GARM_UNIT" --no-pager \
      | grep -q 'found valid runner tools.*arch=s390x'; do
    if (( SECONDS > deadline )); then
      echo "::error::GARM found no s390x tools at ${TOOLS_METADATA_URL} within 15 minutes; check the GARM log for fetch errors."
      return 1
    fi
    sleep 10
  done
  echo "GARM has s390x runner tools from ${TOOLS_METADATA_URL}"
}

diagnostics() {
  echo "::group::GARM scale set runners"
  if [ -n "${SCALESET_ID:-}" ]; then
    garm-cli scaleset runner list "$SCALESET_ID" || true
  fi
  echo "::endgroup::"
  echo "::group::LXD instances"
  sudo lxc list || true
  echo "::endgroup::"
  echo "::group::Runner tools GARM resolved (s390x)"
  sudo journalctl -u "$GARM_UNIT" --no-pager | grep -i -E "s390x|tools" | tail -n 50 | redact || true
  echo "::endgroup::"
  echo "::group::garm-agent connections"
  sudo journalctl -u "$GARM_UNIT" --no-pager | grep -i "agent" | tail -n 50 | redact || true
  echo "::endgroup::"
  echo "::group::GARM log (tail)"
  sudo journalctl -u "$GARM_UNIT" --no-pager | tail -n 300 | redact || true
  echo "::endgroup::"
  local instance
  for instance in $(sudo lxc list --format csv -c n 2>/dev/null); do
    echo "::group::cloud-init output of ${instance}"
    sudo lxc exec "$instance" -- tail -n 200 /var/log/cloud-init-output.log | redact || true
    echo "::endgroup::"
    # cloud-init ends at starting the runner service; whether the runner then
    # connected to GitHub is only in the service's own logs.
    echo "::group::runner service of ${instance}"
    sudo lxc exec "$instance" -- sh -c '
      systemctl status --no-pager "actions.runner.*"
      journalctl --no-pager -u "actions.runner.*" | tail -n 150
      for f in /home/*/actions-runner/_diag/Runner_*.log; do
        echo "== $f"; tail -n 150 "$f"
      done' 2>&1 | redact || true
    echo "::endgroup::"
  done
}

# The VM is ephemeral, so only the GitHub registrations can outlive it: the
# runners, and the scale set itself. GARM only deletes a disabled scale set
# with no runners left, and deleting it removes its registration on GitHub.
teardown() {
  [ -n "${SCALESET_ID:-}" ] || return 0
  garm-cli scaleset update "$SCALESET_ID" --enabled=false || true
  local runner
  for runner in $(scaleset_runners); do
    garm-cli runner delete "$runner" --force-remove-runner || true
  done
  local deadline=$((SECONDS + 120))
  while [ -n "$(scaleset_runners)" ] && (( SECONDS < deadline )); do
    sleep 5
  done
  garm-cli scaleset delete "$SCALESET_ID" || true
}

scaleset_runners() {
  garm-cli scaleset runner list "$SCALESET_ID" --format json 2>/dev/null | jq -r '.[]?.name'
}

# This repo's logs are public. GARM's install script runs under set -x, so its
# output carries the instance's bearer token for GARM's callback/metadata API.
redact() {
  sed -E \
    -e 's/(Bearer|BEARER_TOKEN=|TOKEN=)[[:space:]]*[^[:space:]"'"'"']+/\1[REDACTED]/Ig' \
    -e 's/("?(token|jwt|password|secret)"?[[:space:]]*[:=][[:space:]]*"?)[^[:space:]",]+/\1[REDACTED]/Ig'
}

random_secret() {
  tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 32 || true
}

retry() {
  local attempts="$1" delay="$2"
  shift 2
  local i
  for ((i = 1; i <= attempts; i++)); do
    "$@" && return 0
    sleep "$delay"
  done
  return 1
}

main "$@"
