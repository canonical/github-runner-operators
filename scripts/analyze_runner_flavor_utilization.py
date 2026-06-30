#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Identify GitHub Actions workflows that are over-provisioned for their actual CPU/RAM usage.

Each ephemeral runner VM ships OpenTelemetry hostmetrics to Prometheus/Mimir. This script
sweeps those metrics across every (repository, workflow) combination and computes peak and
average resource utilization. Given a flavor catalog it then recommends the smallest flavor
each workflow's runs would still fit into — exposing which workflows can move to a cheaper VM.

Credentials are not required for --print-queries / --dry-run; all other modes need
--grafana-url (or GRAFANA_URL) and --token (or GRAFANA_TOKEN).
"""

import argparse
import csv
import json
import math
import os
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments, run queries, aggregate, and emit output."""
    args = _build_arg_parser().parse_args()

    repo_filter = (
        f',github_repository=~"{args.repository}"' if args.repository else ""
    )
    w = args.window
    g4 = "github_repository, github_workflow, github_run_id, github_run_attempt"

    queries = _build_queries(g4, repo_filter, w)

    if args.print_queries:
        for label, q in queries.items():
            print(f"# {label}")
            print(q)
            print()
        return

    grafana_url, token = _require_credentials(args)
    uid = args.datasource_uid or _discover_datasource_uid(grafana_url, token, args.verbose)

    if args.verbose:
        print(f"[v] datasource uid: {uid}", file=sys.stderr)

    raw_vectors: dict[str, list[dict]] = {}
    for label, q in queries.items():
        if args.verbose:
            print(f"[v] querying: {label}", file=sys.stderr)
        raw_vectors[label] = _run_instant_query(grafana_url, token, uid, q, args.verbose)

    per_run = _join_vectors(raw_vectors)
    groups = _aggregate_by_workflow(per_run, args.min_runs)

    flavors = _load_flavors(args.flavors) if args.flavors else []
    rows = _build_output_rows(groups, flavors, args.headroom)

    _emit(rows, args.format, args.output)


# ---------------------------------------------------------------------------
# PromQL query construction
# ---------------------------------------------------------------------------


def _build_queries(g4: str, repo_filter: str, window: str) -> dict[str, str]:
    """Return the six instant PromQL queries keyed by a short label.

    All queries use range-vector functions directly on gauges/counters — no
    max_over_time(<subquery>) — so they are cheap instant queries whose heavy
    lifting happens server-side and results are joined in Python.
    """
    # repo_filter is either "" or ',github_repository=~"<regex>"'.
    # bare strips the leading comma so it can open a selector block by itself.
    # Appending repo_filter directly after an existing label (e.g. state="idle")
    # produces the correct PromQL in both the filtered and unfiltered case.
    f = repo_filter
    bare = f.lstrip(",")

    # system_cpu_logical_count is a gauge emitted once per scrape, so
    # max_over_time gives the provisioned vCPU count across the run window.
    prov_cores = f"max by ({g4}) (max_over_time(system_cpu_logical_count{{{bare}}}[{window}]))"

    # system_cpu_load_average_1m is a gauge (one series per host, i.e. per
    # ephemeral VM), so max_over_time is a plain range-vector op — no subquery
    # needed. On Linux it includes I/O-wait, so it over- rather than
    # under-estimates need, which is a safe bias for a "can we shrink?" tool.
    peak_load = f"max by ({g4}) (max_over_time(system_cpu_load_average_1m{{{bare}}}[{window}]))"

    # Idle/total increase ratio cancels the rate-extrapolation factor that
    # Prometheus applies at series boundaries — critical for ephemeral VMs
    # whose series start and end mid-scrape-interval, where plain rate() would
    # systematically under-report utilization.
    avg_cpu_util = (
        f'1 - ( sum by ({g4}) (increase(system_cpu_time_seconds_total{{state="idle"{f}}}[{window}]))'
        f" / sum by ({g4}) (increase(system_cpu_time_seconds_total{{{bare}}}[{window}])) )"
    )

    # system_memory_usage_bytes{state="used"} is a single series per host, so
    # max_over_time is again a plain range-vector op.
    peak_mem = f'max by ({g4}) (max_over_time(system_memory_usage_bytes{{state="used"{f}}}[{window}]))'
    avg_mem  = f'max by ({g4}) (avg_over_time(system_memory_usage_bytes{{state="used"{f}}}[{window}]))'

    # Sum over all memory states (used, free, cached, buffered, …) gives total
    # provisioned RAM because those states partition the physical memory.
    prov_ram = f"sum by ({g4}) (avg_over_time(system_memory_usage_bytes{{{bare}}}[{window}]))"

    # Fallback core count for collectors that don't emit system_cpu_logical_count:
    # system_cpu_time_seconds_total carries one series per (cpu, state), so counting
    # the distinct cpu label values per run yields the logical CPU count.
    cores_fallback = (
        f"count by ({g4}) (count by ({g4}, cpu) "
        f"(max_over_time(system_cpu_time_seconds_total{{{bare}}}[{window}])))"
    )

    return {
        "prov_cores": prov_cores,
        "peak_load": peak_load,
        "avg_cpu_util": avg_cpu_util,
        "peak_mem": peak_mem,
        "avg_mem": avg_mem,
        "prov_ram": prov_ram,
        "cores_fallback": cores_fallback,
    }


# ---------------------------------------------------------------------------
# Grafana / Prometheus access
# ---------------------------------------------------------------------------


def _require_credentials(args: argparse.Namespace) -> tuple[str, str]:
    """Return (grafana_url, token), exiting with a clear message if absent."""
    url = args.grafana_url or os.environ.get("GRAFANA_URL", "")
    token = args.token or os.environ.get("GRAFANA_TOKEN", "")
    missing = []
    if not url:
        missing.append("--grafana-url / GRAFANA_URL")
    if not token:
        missing.append("--token / GRAFANA_TOKEN")
    if missing:
        sys.exit(f"error: missing required credentials: {', '.join(missing)}")
    return url.rstrip("/"), token


def _discover_datasource_uid(grafana_url: str, token: str, verbose: bool) -> str:
    """Return the UID of the best-match Prometheus datasource.

    Prefers a datasource whose name contains 'mimir' or 'prometheus'
    (case-insensitive); falls back to the first datasource of type 'prometheus'.
    """
    data = _grafana_get(grafana_url, token, "/api/datasources")
    prometheus_ds = [d for d in data if d.get("type") == "prometheus"]
    if not prometheus_ds:
        sys.exit("error: no Prometheus datasource found in Grafana")

    preferred = [
        d for d in prometheus_ds
        if any(kw in d.get("name", "").lower() for kw in ("mimir", "prometheus"))
    ]
    chosen = preferred[0] if preferred else prometheus_ds[0]

    if verbose:
        print(f"[v] auto-selected datasource: {chosen.get('name')} ({chosen.get('uid')})", file=sys.stderr)
    return chosen["uid"]


def _run_instant_query(
    grafana_url: str, token: str, uid: str, query: str, verbose: bool
) -> list[dict]:
    """Execute one instant PromQL query and return the result list."""
    path = f"/api/datasources/proxy/uid/{uid}/api/v1/query"
    params = urllib.parse.urlencode({"query": query})
    data = _grafana_get(grafana_url, token, f"{path}?{params}")
    results = data.get("data", {}).get("result", [])
    if verbose:
        print(f"[v]   → {len(results)} series returned", file=sys.stderr)
    return results


def _grafana_get(grafana_url: str, token: str, path: str) -> Any:
    """Make an authenticated GET to Grafana and return the parsed JSON body."""
    url = grafana_url + path
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        sys.exit(f"error: HTTP {exc.code} from {url}: {exc.read().decode(errors='replace')}")
    except urllib.error.URLError as exc:
        sys.exit(f"error: could not reach {url}: {exc.reason}")
    return json.loads(body)


# ---------------------------------------------------------------------------
# Data joining and aggregation
# ---------------------------------------------------------------------------

# Key identifying a single workflow run: (repo, workflow, run_id, run_attempt)
_RunKey = tuple[str, str, str, str]
# Key identifying a workflow across runs: (repo, workflow)
_WorkflowKey = tuple[str, str]


def _join_vectors(raw_vectors: dict[str, list[dict]]) -> dict[_RunKey, dict]:
    """Join the six query result vectors on the g4 label set into per-run records."""
    per_run: dict[_RunKey, dict] = {}

    def _key(metric: dict) -> _RunKey:
        return (
            metric.get("github_repository", ""),
            metric.get("github_workflow", ""),
            metric.get("github_run_id", ""),
            metric.get("github_run_attempt", ""),
        )

    def _val(series: dict) -> float | None:
        v = series.get("value")
        if v and len(v) == 2:
            try:
                return float(v[1])
            except (ValueError, TypeError):
                return None
        return None

    for label, series_list in raw_vectors.items():
        for series in series_list:
            k = _key(series["metric"])
            if not all(k):
                continue
            per_run.setdefault(k, {})[label] = _val(series)

    # Use the derived cpu-count fallback wherever system_cpu_logical_count was
    # absent, so downstream sizing still has a provisioned core count to compare.
    for metrics in per_run.values():
        if metrics.get("prov_cores") is None and metrics.get("cores_fallback") is not None:
            metrics["prov_cores"] = metrics["cores_fallback"]

    return per_run


def _aggregate_by_workflow(
    per_run: dict[_RunKey, dict], min_runs: int
) -> dict[_WorkflowKey, dict]:
    """Group per-run records into per-(repo, workflow) statistics."""
    buckets: dict[_WorkflowKey, list[dict]] = {}
    for (repo, workflow, _run_id, _attempt), metrics in per_run.items():
        buckets.setdefault((repo, workflow), []).append(metrics)

    groups: dict[_WorkflowKey, dict] = {}
    for (repo, workflow), run_metrics in buckets.items():
        n = len(run_metrics)
        if n < min_runs:
            continue

        def _collect(key: str) -> list[float]:
            return [m[key] for m in run_metrics if m.get(key) is not None]

        peak_loads = _collect("peak_load")
        peak_mems = _collect("peak_mem")
        avg_utils = _collect("avg_cpu_util")
        avg_mems = _collect("avg_mem")
        prov_cores_vals = _collect("prov_cores")
        prov_ram_vals = _collect("prov_ram")

        # p95 across runs for per-run peak values: safe headroom for rare spikes.
        # Fall back to max when n is too small for quantiles (need at least 2).
        peak_load_p95 = _p95_or_max(peak_loads)
        peak_mem_p95 = _p95_or_max(peak_mems)

        groups[(repo, workflow)] = {
            "runs": n,
            "prov_cores": max(prov_cores_vals) if prov_cores_vals else None,
            "prov_ram": max(prov_ram_vals) if prov_ram_vals else None,
            "peak_load_p95": peak_load_p95,
            "peak_mem_p95": peak_mem_p95,
            "avg_cpu_util": statistics.mean(avg_utils) if avg_utils else None,
            "avg_mem_util": (
                statistics.mean(avg_mems) / max(prov_ram_vals)
                if avg_mems and prov_ram_vals
                else None
            ),
        }

    return groups


def _p95_or_max(values: list[float]) -> float | None:
    """Return the p95 of values, falling back to max when n < 2."""
    if not values:
        return None
    if len(values) < 2:
        return values[0]
    # statistics.quantiles requires n >= 2; n=4 cuts give quartiles, n=100 gives percentiles.
    cuts = statistics.quantiles(values, n=100, method="inclusive")
    return cuts[94]  # 0-indexed: index 94 = 95th percentile


# ---------------------------------------------------------------------------
# Flavor catalog
# ---------------------------------------------------------------------------


def _load_flavors(path: str) -> list[dict]:
    """Load and normalize a flavor catalog from a JSON file.

    Accepts both the `openstack flavor list -f json` shape (list of objects with
    capitalized keys like Name/VCPUs/RAM) and a plain list with lowercase keys
    (name/vcpus/ram). RAM is in MiB (OpenStack convention) and is converted to
    bytes here so downstream comparisons use consistent units.
    """
    try:
        with open(path) as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"error: could not load flavor file {path!r}: {exc}")

    flavors = []
    for item in raw:
        # Normalize keys case-insensitively
        lowered = {k.lower(): v for k, v in item.items()}
        name = lowered.get("name")
        vcpus = lowered.get("vcpus")
        ram_mib = lowered.get("ram")
        if name is None or vcpus is None or ram_mib is None:
            continue
        flavors.append(
            {
                "name": str(name),
                "vcpus": int(vcpus),
                "ram_bytes": int(ram_mib) * 1024 * 1024,  # MiB → bytes
                "disk": lowered.get("disk"),
            }
        )

    if not flavors:
        sys.exit(f"error: flavor file {path!r} contained no usable entries")

    # Pre-sort so the selection loop's "first fit" gives the smallest flavor.
    flavors.sort(key=lambda f: (f["vcpus"], f["ram_bytes"]))
    return flavors


def _recommend_flavor(
    cores_needed: float,
    ram_needed: float,
    flavors: list[dict],
) -> dict | None:
    """Return the smallest flavor with vcpus >= cores_needed and ram >= ram_needed."""
    for f in flavors:  # already sorted smallest-first
        if f["vcpus"] >= cores_needed and f["ram_bytes"] >= ram_needed:
            return f
    return None


def _identify_current_flavor(
    prov_cores: float | None,
    prov_ram: float | None,
    flavors: list[dict],
) -> dict | None:
    """Reverse-map measured provisioned resources back to a catalog flavor.

    The metrics carry no flavor label, so the flavor a workflow selected is
    inferred from its resource shape: vCPU count matches the logical-core count
    exactly, while measured total RAM sits slightly below the advertised flavor
    RAM (kernel/firmware reserve some), so among same-vCPU flavors we pick the
    one whose advertised RAM is nearest the measurement.
    """
    if not flavors or prov_cores is None or prov_ram is None:
        return None
    cores = round(prov_cores)
    candidates = [f for f in flavors if f["vcpus"] == cores] or flavors
    return min(candidates, key=lambda f: abs(f["ram_bytes"] - prov_ram))


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _build_output_rows(
    groups: dict[_WorkflowKey, dict],
    flavors: list[dict],
    headroom: float,
) -> list[dict]:
    """Compute recommendation columns and produce a sorted list of row dicts."""
    rows = []
    for (repo, workflow), g in groups.items():
        peak_load_p95 = g.get("peak_load_p95")
        peak_mem_p95 = g.get("peak_mem_p95")
        prov_cores = g.get("prov_cores")
        prov_ram = g.get("prov_ram")
        avg_cpu = g.get("avg_cpu_util")
        avg_mem = g.get("avg_mem_util")

        rec_name = rec_vcpus = rec_ram_gb = downsize = "N/A"

        current = _identify_current_flavor(prov_cores, prov_ram, flavors)
        current_name = current["name"] if current else "N/A"

        if flavors and peak_load_p95 is not None and peak_mem_p95 is not None:
            cores_needed = math.ceil(peak_load_p95 * (1 + headroom))
            ram_needed = peak_mem_p95 * (1 + headroom)
            rec = _recommend_flavor(cores_needed, ram_needed, flavors)
            if rec:
                rec_name = rec["name"]
                rec_vcpus = rec["vcpus"]
                rec_ram_gb = round(rec["ram_bytes"] / (1024 ** 3), 2)
                downsize = "Y" if (
                    (prov_cores is not None and rec["vcpus"] < prov_cores)
                    or (prov_ram is not None and rec["ram_bytes"] < prov_ram)
                ) else "N"
            else:
                rec_name = "none-fits"

        rows.append(
            {
                "repository": repo,
                "workflow": workflow,
                "runs": g["runs"],
                "prov_cores": _fmt_val(prov_cores, ".0f"),
                "prov_ram_gb": _fmt_bytes_gb(prov_ram),
                "p95_peak_load": _fmt_val(peak_load_p95, ".2f"),
                "avg_cpu_util%": _fmt_pct(avg_cpu),
                "p95_peak_mem_gb": _fmt_bytes_gb(peak_mem_p95),
                "avg_mem%": _fmt_pct(avg_mem),
                "current_flavor": current_name,
                "recommended_flavor": rec_name,
                "rec_vcpus": rec_vcpus,
                "rec_ram_gb": rec_ram_gb,
                "downsize": downsize,
            }
        )

    # Biggest downsizes / lowest utilization first: sort by avg_cpu_util% ascending.
    rows.sort(key=lambda r: float(r["avg_cpu_util%"].rstrip("%")) if r["avg_cpu_util%"] not in ("N/A", "") else 999)
    return rows


def _emit(rows: list[dict], fmt: str, output_path: str | None) -> None:
    """Write rows in the requested format to stdout or a file."""
    fh = open(output_path, "w", newline="") if output_path else sys.stdout
    try:
        if fmt == "json":
            json.dump(rows, fh, indent=2)
            fh.write("\n")
        elif fmt == "csv":
            if not rows:
                return
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        else:  # table
            if not rows:
                print("(no data)", file=fh)
                return
            _print_table(rows, fh)
    finally:
        if output_path:
            fh.close()


def _print_table(rows: list[dict], fh: Any) -> None:
    """Print an aligned text table."""
    cols = list(rows[0].keys())
    widths = {c: len(c) for c in cols}
    for row in rows:
        for c in cols:
            widths[c] = max(widths[c], len(str(row[c])))

    header = "  ".join(c.ljust(widths[c]) for c in cols)
    separator = "  ".join("-" * widths[c] for c in cols)
    print(header, file=fh)
    print(separator, file=fh)
    for row in rows:
        print("  ".join(str(row[c]).ljust(widths[c]) for c in cols), file=fh)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_val(v: float | None, spec: str) -> str:
    return format(v, spec) if v is not None else "N/A"


def _fmt_bytes_gb(v: float | None) -> str:
    return f"{v / (1024 ** 3):.2f}" if v is not None else "N/A"


def _fmt_pct(v: float | None) -> str:
    return f"{v * 100:.1f}%" if v is not None else "N/A"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Analyze GitHub Actions runner CPU/RAM utilization from Grafana/Prometheus "
            "hostmetrics and recommend smaller VM flavors where possible."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Print PromQL queries without hitting the network:
  %(prog)s --print-queries --window 7d

  # Full analysis for all repositories (requires credentials):
  %(prog)s --grafana-url https://grafana.example.com --token $TOKEN \\
           --flavors openstack-flavors.json

  # Filter to a specific org and output CSV:
  %(prog)s --repository 'canonical/.*' --format csv --output report.csv
""",
    )
    p.add_argument("--grafana-url", metavar="URL", default="",
                   help="Grafana base URL (env: GRAFANA_URL)")
    p.add_argument("--token", metavar="TOKEN", default="",
                   help="Grafana service-account token (env: GRAFANA_TOKEN)")
    p.add_argument("--datasource-uid", metavar="UID",
                   help="Prometheus/Mimir datasource UID (auto-discovered if omitted)")
    p.add_argument("--window", metavar="DURATION", default="14d",
                   help="Look-back window for PromQL range vectors (default: 14d)")
    p.add_argument("--repository", metavar="REGEX",
                   help="Filter by github_repository label (PromQL regex, e.g. 'canonical/.*')")
    p.add_argument("--flavors", metavar="FILE",
                   help="JSON flavor catalog for right-sizing recommendations")
    p.add_argument("--headroom", type=float, default=0.3, metavar="FRACTION",
                   help="Safety headroom fraction added to resource requirements (default: 0.3)")
    p.add_argument("--min-runs", type=int, default=5, metavar="N",
                   help="Minimum run count to include a workflow in output (default: 5)")
    p.add_argument("--format", choices=("table", "csv", "json"), default="table",
                   help="Output format (default: table)")
    p.add_argument("--output", metavar="FILE",
                   help="Write output to FILE instead of stdout")
    p.add_argument("--print-queries", "--dry-run", action="store_true",
                   help="Print the PromQL queries and exit (no credentials needed)")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Print diagnostic messages to stderr")
    return p


if __name__ == "__main__":
    main()
