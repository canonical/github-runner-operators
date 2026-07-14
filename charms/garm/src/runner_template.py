# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Render runner-behaviour options into a GARM runner-install template.

GARM stores the runner-install script as a server-side template that a
scaleset references by ``template_id``. Three of the six operator-facing runner
options (docker mirror, telemetry, pre-job hook) are delivered by copying GARM's
system ``github_linux`` template and injecting two blocks right after the
shebang — before the base template's ``set -e`` — so a best-effort step can never
abort the whole bootstrap:

  * a *pre-install* block that runs before the runner is installed, as the
    unprivileged ``runner`` user, escalating each privileged step with ``sudo``
    (docker registry mirror, static host prep), and
  * a *runner job hooks* block that writes the GitHub job-start hook and the
    runner ``.env`` file under ``/home/runner/actions-runner``.

The proxy/aproxy option is *not* injected into this template: GARM prepends a
compiled-in wrapper script that curls this template from the GARM metadata API
before any of its content runs, so proxy bootstrap embedded in the template
could never help that curl succeed on a proxy-only network. It is instead
rendered by :func:`render_aproxy_pre_install_script` and delivered as a
``pre_install_scripts`` extra-spec entry (see ``scaleset_reconciler``), which
GARM runs, as root, before the wrapper.

The reconciler creates/updates the per-scaleset template with the bytes returned
by :func:`build_template_data` and only does so when :meth:`RunnerConfig.has_config`
is true.

Blocks are rendered from Jinja2 templates in ``src/templates/*.j2``, loaded via a
``FileSystemLoader`` rooted next to this module; ``src/`` is packed verbatim into
the rock, so the template files ship alongside the charm code. ``autoescape`` is
off throughout: the output is shell/YAML, not HTML.
"""

import json
import pathlib
import shlex
import urllib.parse

import jinja2

from charm_state import RunnerConfig
from runner_paths import (
    PRE_JOB_HOOK_PATH,
    RUNNER_ENV_PATH,
    RUNNER_HOME,
    RUNNER_USER,
    prepend_after_shebang,
)

_TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"
_JINJA_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
    undefined=jinja2.StrictUndefined,
)

# OpenTelemetry collector config: hostmetrics/otlp/loki pipelines exporting to
# the configured endpoint. `$GITHUB_*`, `$RUNNER_NAME` and `$(uname -m)` are left
# as literal shell syntax — they sit inside the *inner*, unquoted `tee <<EOF`
# heredoc, so they only expand when the runner executes this hook, once per job.
# Only the exporter endpoint is substituted at render time.
_OTEL_COLLECTOR_SETUP_TEMPLATE = _JINJA_ENV.get_template("otel_collector_setup.j2")

# Dense inline conditionals: `trim_blocks` unconditionally eats exactly one
# newline right after every `{% %}` tag, so a tag-only line contributes nothing
# to the output regardless of which branch runs — that's what lets the
# optional blocks below disappear cleanly (no stray blank line) when unset.
_HOOK_BODY_TEMPLATE = _JINJA_ENV.get_template("hook_body.j2")
_CUSTOM_PRE_JOB_SCRIPT_TEMPLATE = _JINJA_ENV.get_template("custom_pre_job_script.j2")
_APROXY_TEMPLATE = _JINJA_ENV.get_template("aproxy.j2")
_DOCKERHUB_MIRROR_TEMPLATE = _JINJA_ENV.get_template("dockerhub_mirror.j2")
_STATIC_HOST_PREP_TEMPLATE = _JINJA_ENV.get_template("static_host_prep.j2")
_PRE_INSTALL_TEMPLATE = _JINJA_ENV.get_template("pre_install.j2")
_PRE_JOB_HOOKS_TEMPLATE = _JINJA_ENV.get_template("pre_job_hooks.j2")


def build_template_data(base: bytes, config: RunnerConfig) -> bytes:
    """Inject the runner-option blocks into a base runner-install template.

    The blocks are inserted immediately after the shebang line (before the base
    template's ``set -e``), mirroring GARM's documented "prepend after the
    shebang" approach.

    Args:
        base: The system ``github_linux`` template bytes to copy from.
        config: The runner options to render.

    Returns:
        The new template bytes, with the pre-install and job-hook blocks injected.
    """
    text = base.decode("utf-8")
    injection = render_pre_install(config) + render_pre_job_hooks(config)
    return prepend_after_shebang(text, injection).encode("utf-8")


def render_pre_install(config: RunnerConfig) -> str:
    """Render the pre-install block (runs before the runner is installed).

    Args:
        config: The runner options to render.

    Returns:
        A bash snippet, terminated by a newline.
    """
    dockerhub = (
        _render_dockerhub_mirror(config.dockerhub_mirror) if config.dockerhub_mirror else ""
    )
    return _PRE_INSTALL_TEMPLATE.render(
        dockerhub=dockerhub, static_prep=_render_static_host_prep()
    )


def render_pre_job_hooks(config: RunnerConfig) -> str:
    """Render the runner ``env`` file and GitHub job-start hook.

    The hook file sets up the OpenTelemetry collector, when configured, and runs
    the operator's ``pre-job-script``. The docker mirror and OTEL endpoint are
    exported via the runner ``env`` file, read once per job by the runner service.

    Args:
        config: The runner options to render.

    Returns:
        A bash snippet, terminated by a newline.
    """
    otel_endpoint = config.otel_collector_endpoint
    dockerhub_mirror = config.dockerhub_mirror

    hook_body = _render_pre_job_hook_body(config, otel_endpoint)

    env_entries = []
    if dockerhub_mirror:
        env_entries.append(f"DOCKERHUB_MIRROR={dockerhub_mirror}")
        env_entries.append(f"CONTAINER_REGISTRY_URL={dockerhub_mirror}")
    env_entries.append(f"ACTIONS_RUNNER_HOOK_JOB_STARTED={PRE_JOB_HOOK_PATH}")
    if otel_endpoint:
        env_entries.append(f"ACTION_OTEL_EXPORTER_OTLP_ENDPOINT={otel_endpoint}")

    # Pick delimiters that don't collide with the (operator-controlled) content,
    # so a pre-job-script containing the literal delimiter can't terminate the
    # heredoc early. Deterministic for a given content, keeping the rendered
    # template stable across reconciles. Computed in Python (two-phase render)
    # since the delimiter depends on the already-rendered hook body.
    prejob_delim = _heredoc_delimiter(hook_body, "GARM_CHARM_PREJOB")
    env_delim = _heredoc_delimiter("\n".join(env_entries), "GARM_CHARM_ENV")
    # Per-scaleset env write: these vars come from the scaleset's RunnerConfig, so
    # they land in the per-scaleset template (a separate .env append from the
    # global tmate one in garm_template.build_tmate_env_snippet).
    return _PRE_JOB_HOOKS_TEMPLATE.render(
        runner_home=RUNNER_HOME,
        hook_path=PRE_JOB_HOOK_PATH,
        env_path=RUNNER_ENV_PATH,
        runner_user=RUNNER_USER,
        hook_body=hook_body,
        env_entries=env_entries,
        prejob_delim=prejob_delim,
        env_delim=env_delim,
    )


def render_aproxy_pre_install_script(config: RunnerConfig) -> str:
    """Render the standalone aproxy bootstrap script.

    The script installs aproxy, points it and the snap store at the configured
    proxy, and writes an nftables DNAT ruleset that transparently redirects
    egress traffic to aproxy's listener, both for locally-initiated connections
    (``output`` chain) and forwarded ones (``prerouting`` chain).

    Args:
        config: The runner options (uses proxy, exclude addresses, redirect ports).

    Returns:
        A complete best-effort bash script (shebang first line, deliberately no
        ``set -e``) configuring aproxy as a transparent forward proxy.
    """
    # Values are already validated at parse time (RunnerConfig.from_databag); only
    # shell-safe embedding (quoting, the empty-string split guard below) happens here.
    ports = [t for t in config.aproxy_redirect_ports.split(",") if t] or ["80", "443"]
    nft_ports = ", ".join(ports)
    excludes = [t for t in config.aproxy_exclude_addresses.split(",") if t]
    exclude_elements = ", ".join(["127.0.0.0/8", *excludes])
    # `\$default-ipv4` stays escaped so the literal two characters `$default-ipv4`
    # land in the file, which nft itself resolves against the `define` above when
    # it loads the file.
    dnat_rule = (
        f"ip daddr != @exclude tcp dport {{ {nft_ports} }} counter dnat to \\$default-ipv4:54969"
    )
    return _APROXY_TEMPLATE.render(
        proxy=shlex.quote(config.runner_http_proxy),
        proxy_host_port=shlex.quote(_proxy_host_port(config.runner_http_proxy)),
        exclude_elements=exclude_elements,
        dnat_rule=dnat_rule,
    )


def _proxy_host_port(proxy: str) -> str:
    """Return the bare authority (``host:port``, optionally ``user:pass@``) of a proxy.

    aproxy rejects a full URL for its ``proxy=`` setting, unlike ``snap set
    system proxy.http/https=``, so it needs the scheme stripped. The URL
    ``netloc`` is returned verbatim, preserving userinfo and IPv6 brackets that
    ``urlsplit().hostname`` would drop. Accepts a URL (``http://host:port``) or
    an already-bare ``host:port``.

    Args:
        proxy: The configured proxy value, with or without a URL scheme.

    Returns:
        The proxy authority with any scheme and path removed.
    """
    candidate = proxy if "//" in proxy else f"//{proxy}"
    return urllib.parse.urlsplit(candidate).netloc


def _render_pre_job_hook_body(config: RunnerConfig, otel_endpoint: str) -> str:
    """Render the contents of the pre-job hook file (the GitHub job-start hook).

    Args:
        config: The runner options to render.
        otel_endpoint: The sanitised OTEL endpoint, or "" if unset.

    Returns:
        The full contents of the hook script (no trailing newline).
    """
    otel = (
        _render_fragment(_OTEL_COLLECTOR_SETUP_TEMPLATE, endpoint=otel_endpoint)
        if otel_endpoint
        else ""
    )
    custom_script = (
        _render_custom_pre_job_script(config.pre_job_script) if config.pre_job_script else ""
    )
    return _render_fragment(_HOOK_BODY_TEMPLATE, otel=otel, custom_script=custom_script)


def _render_fragment(template: jinja2.Template, **kwargs: object) -> str:
    """Render a sub-fragment for splicing into a larger script.

    Fragment template files end with a newline (POSIX text-file convention), but
    a fragment is spliced into a composing template (``pre_install.j2`` /
    ``hook_body.j2`` / ``pre_job_hooks.j2``) that owns the spacing between blocks.
    Its own trailing newline would leak an extra blank line into the composition,
    so drop it here; the composer supplies the separator.

    Args:
        template: The fragment template to render.
        kwargs: The template variables.

    Returns:
        The rendered fragment without its trailing newline.
    """
    return template.render(**kwargs).removesuffix("\n")


def _heredoc_delimiter(content: str, base: str) -> str:
    """Return a heredoc delimiter that does not appear as a line in *content*.

    Args:
        content: The heredoc body the delimiter must not collide with.
        base: The preferred delimiter; extended only if it collides.

    Returns:
        ``base``, suffixed with underscores until no line of *content* matches it.
    """
    lines = content.splitlines()
    delimiter = base
    while delimiter in lines:
        delimiter += "_"
    return delimiter


def _render_custom_pre_job_script(script: str) -> str:
    """Render the custom pre-job script block.

    Writes the operator script to a temp file, runs it, and removes it — a
    failure is logged but never aborts the job.

    Args:
        script: The operator-provided pre-job-script content, inserted verbatim
            (mirrors the template's ``| safe`` filter).

    Returns:
        A bash snippet.
    """
    delim = _heredoc_delimiter(script, "GARM_CHARM_CUSTOM_PREJOB")
    return _render_fragment(_CUSTOM_PRE_JOB_SCRIPT_TEMPLATE, delim=delim, script=script)


def _render_dockerhub_mirror(mirror: str) -> str:
    """Render Docker daemon config pointing at the registry mirror.

    Args:
        mirror: The registry mirror URL.

    Returns:
        A bash snippet writing /etc/docker/daemon.json and restarting docker.
    """
    daemon_json = json.dumps({"registry-mirrors": [mirror]})
    return _render_fragment(_DOCKERHUB_MIRROR_TEMPLATE, daemon_json=daemon_json)


def _render_static_host_prep() -> str:
    """Render the always-on host-preparation steps.

    Adds the runner account to the ``lxd`` and ``adm`` groups.

    Returns:
        A bash snippet. Each command is guarded by ``|| true`` so it is a no-op
        if the runner account doesn't exist yet.
    """
    return _render_fragment(_STATIC_HOST_PREP_TEMPLATE, runner_user=RUNNER_USER)
