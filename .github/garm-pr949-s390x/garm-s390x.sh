#!/usr/bin/env bash
# Throwaway harness for testing cloudbase/garm#949 on s390x.
#
# Runs GARM, built from the PR, on this s390x runner with a patched LXD provider,
# and has it boot one s390x LXD container that registers as a runner of this repo
# with the tools Canonical publishes. The workflow then routes a job to it.
#
# Usage: garm-s390x.sh setup|diagnostics|teardown
#
# Required env: GARM_SHA, PROVIDER_LXD_SHA, PROVIDER_COMMON_SHA, RUNNER_LABEL,
# TOOLS_METADATA_URL, GITHUB_REPOSITORY, GITHUB_TOKEN, E2E_GITHUB_APP_ID,
# E2E_GITHUB_APP_INSTALLATION_ID, E2E_GITHUB_APP_PRIVATE_KEY.

set -euo pipefail
# The App key, the DB passphrase and the admin password all land in files here.
umask 077

WORK="${RUNNER_TEMP:-/tmp}/garm-pr949"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GARM_PORT=9997
GARM_UNIT=garm-pr949
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
  sudo apt-get -qq install -y build-essential jq netcat-openbsd

  build_garm
  build_provider
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

# The released provider rejects s390x twice: its own LXD arch map, and the
# GetTools check in garm-provider-common v0.1.9. The patch fixes the first, the
# common bump to the commit #949 vendors fixes the second.
build_provider() {
  echo "::group::Build patched garm-provider-lxd at ${PROVIDER_LXD_SHA}"
  fetch_at cloudbase/garm-provider-lxd "$PROVIDER_LXD_SHA" "$WORK/garm-provider-lxd"
  (
    cd "$WORK/garm-provider-lxd"
    git apply "$HERE/garm-provider-lxd-arches.patch"
    go get "github.com/cloudbase/garm-provider-common@${PROVIDER_COMMON_SHA}"
    go build -mod=mod -o "$WORK/garm-provider-lxd.bin" .
  )
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
description = "Local LXD with s390x patched provider"
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
  local password private_key repo_id pool_id
  password="$(random_secret)"
  echo "::add-mask::${password}"
  printf '%s' "$password" > "$WORK/admin-password"
  garm-cli init --name local --url "http://${BRIDGE_IP}:${GARM_PORT}" \
    --username admin --email admin@example.invalid --full-name admin \
    --password-file "$WORK/admin-password"

  # The behaviour under test: the extra-arch tools source on the endpoint.
  garm-cli github endpoint update github.com --tools-metadata-url "$TOOLS_METADATA_URL"
  garm-cli github endpoint show github.com

  private_key="$WORK/app.pem"
  # Same normalisation garm_e2e.yaml applies: the secret may be PEM or base64.
  case "$E2E_GITHUB_APP_PRIVATE_KEY" in
    *-----BEGIN*) printf '%s\n' "$E2E_GITHUB_APP_PRIVATE_KEY" > "$private_key" ;;
    *) printf '%s' "$E2E_GITHUB_APP_PRIVATE_KEY" | base64 -d > "$private_key" ;;
  esac
  chmod 600 "$private_key"
  garm-cli github credentials add --name e2e-app --description "garm#949 s390x test" \
    --endpoint github.com --auth-type app \
    --app-id "$E2E_GITHUB_APP_ID" --app-installation-id "$E2E_GITHUB_APP_INSTALLATION_ID" \
    --private-key-path "$private_key"
  rm -f "$private_key"

  repo_id="$(garm-cli repo add --owner "${GITHUB_REPOSITORY%%/*}" --name "${GITHUB_REPOSITORY#*/}" \
    --credentials e2e-app --random-webhook-secret --format json | jq -r .id)"

  # No webhook reaches this host, so a warm idle runner is what picks up the
  # queued job; max 1 keeps GARM from booting more once that runner is consumed.
  pool_id="$(garm-cli pool add --repo "$repo_id" --provider-name lxd_local \
    --image "$IMAGE" --flavor default --os-type linux --os-arch s390x \
    --tags "$RUNNER_LABEL" --min-idle-runners 1 --max-runners 1 --enabled \
    --format json | jq -r .id)"
  echo "POOL_ID=${pool_id}" >> "${GITHUB_ENV:-/dev/null}"
  garm-cli pool show "$pool_id"
  echo "::endgroup::"
}

diagnostics() {
  echo "::group::GARM runners"
  garm-cli runner list --long || true
  echo "::endgroup::"
  echo "::group::LXD instances"
  sudo lxc list || true
  echo "::endgroup::"
  echo "::group::Runner tools GARM resolved (s390x)"
  sudo journalctl -u "$GARM_UNIT" --no-pager | grep -i -E "s390x|tools" | tail -n 50 | redact || true
  echo "::endgroup::"
  echo "::group::GARM log (tail)"
  sudo journalctl -u "$GARM_UNIT" --no-pager | tail -n 300 | redact || true
  echo "::endgroup::"
  local instance
  for instance in $(sudo lxc list --format csv -c n 2>/dev/null); do
    echo "::group::cloud-init output of ${instance}"
    sudo lxc exec "$instance" -- tail -n 200 /var/log/cloud-init-output.log | redact || true
    echo "::endgroup::"
  done
}

# The VM is ephemeral, so only the GitHub registrations can outlive it. GARM
# deletes those when it removes its runners; anything it misses is an offline
# ephemeral runner GitHub reaps on its own.
teardown() {
  if [ -n "${POOL_ID:-}" ]; then
    garm-cli pool update "$POOL_ID" --enabled=false --min-idle-runners 0 || true
  fi
  local runner
  for runner in $(garm-cli runner list --format json 2>/dev/null | jq -r '.[].name'); do
    garm-cli runner delete "$runner" --force-remove-runner || true
  done
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
