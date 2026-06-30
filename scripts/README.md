# scripts/

Utility scripts for the github-runner-operators monorepo.

## Flavor right-sizing

`analyze_runner_flavor_utilization.py` sweeps Grafana/Prometheus hostmetrics for every
(repository, workflow) combination and identifies workflows whose runner VMs are
over-provisioned — i.e., workflows that could run on a smaller, cheaper flavor.

### Prerequisites

- A Grafana service-account token with `datasources:query` permission.
- The Prometheus/Mimir datasource must contain `system_cpu_*` and `system_memory_*`
  metrics emitted by the OpenTelemetry hostmetrics receiver running on each runner VM.

### Usage

```bash
# Print the PromQL queries without hitting the network (useful for inspection):
./analyze_runner_flavor_utilization.py --print-queries --window 7d

# Full analysis for all repositories:
./analyze_runner_flavor_utilization.py \
    --grafana-url https://grafana.example.com \
    --token "$GRAFANA_TOKEN" \
    --flavors openstack-flavors.json

# Narrow to one org, output CSV:
./analyze_runner_flavor_utilization.py \
    --grafana-url https://grafana.example.com \
    --token "$GRAFANA_TOKEN" \
    --flavors openstack-flavors.json \
    --repository 'canonical/.*' \
    --format csv --output report.csv
```

Credentials can also be provided via environment variables `GRAFANA_URL` and
`GRAFANA_TOKEN` instead of flags.

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--grafana-url` | `$GRAFANA_URL` | Grafana base URL |
| `--token` | `$GRAFANA_TOKEN` | Grafana service-account token |
| `--datasource-uid` | auto-discovered | Prometheus/Mimir datasource UID |
| `--window` | `14d` | Look-back window (PromQL duration string) |
| `--repository` | all | Filter by `github_repository` label (PromQL regex) |
| `--flavors` | none | JSON flavor catalog (see below) |
| `--flavor-name-filter` | none | Regex restricting the catalog to real runner flavors (e.g. `^github-runner-`) |
| `--headroom` | `0.3` | Safety margin added to resource requirements (30 %) |
| `--min-runs` | `5` | Minimum run count to include a workflow in the report |
| `--format` | `table` | Output format: `table`, `csv`, `json`, or `summary` |
| `--output` | stdout | Write output to a file |
| `--print-queries` / `--dry-run` | — | Print PromQL and exit; no credentials needed |
| `-v` | — | Verbose diagnostic output to stderr |

### Flavor catalog format

The `--flavors` file must be a JSON array. Two shapes are accepted:

**OpenStack `flavor list -f json` shape** (keys capitalized, RAM in MiB):

```json
[
  {"ID": "1", "Name": "m1.small",  "VCPUs": 2, "RAM": 2048, "Disk": 20},
  {"ID": "2", "Name": "m1.medium", "VCPUs": 4, "RAM": 4096, "Disk": 40},
  {"ID": "3", "Name": "m1.large",  "VCPUs": 8, "RAM": 8192, "Disk": 80}
]
```

**Plain lowercase shape** (RAM in MiB, `disk` is optional):

```json
[
  {"name": "small",  "vcpus": 2, "ram": 2048},
  {"name": "medium", "vcpus": 4, "ram": 4096},
  {"name": "large",  "vcpus": 8, "ram": 8192}
]
```

`RAM` is always interpreted as MiB (OpenStack convention). Mixed capitalisation is
handled case-insensitively.

### Output columns

| Column | Description |
|--------|-------------|
| `repository` | GitHub repository (`owner/repo`) |
| `workflow` | Workflow name |
| `runs` | Number of observed runs |
| `prov_cores` | Provisioned vCPU count |
| `prov_ram_gb` | Provisioned RAM (GiB) |
| `p95_peak_load` | p95 of per-run peak 1-minute load average |
| `avg_cpu_util%` | Mean CPU utilization across runs |
| `p95_peak_mem_gb` | p95 of per-run peak memory usage (GiB) |
| `avg_mem%` | Mean memory utilization across runs |
| `current_flavor` | Catalog flavor matching the measured shape (see note) |
| `recommended_flavor` | Smallest flavor that fits (or `none-fits` / `N/A`) |
| `rec_vcpus` | vCPUs of recommended flavor |
| `rec_ram_gb` | RAM of recommended flavor (GiB) |
| `verdict` | `downsize`, `upsize`, `mixed`, `ok`, or `none-fits` (recommended vs current flavor) |

Rows are sorted lowest average CPU utilization first so the biggest
right-sizing opportunities appear at the top. `--format summary` collapses the
whole report into verdict counts, the `p95_peak_load` distribution, and the top
`downsize` transitions — handy for a quick "how over-provisioned are we?" read.

> **Catalog hygiene.** `verdict` compares the recommended flavor against the
> `current_flavor`, so only entries runners can actually launch belong in the
> catalog. A wholesale `openstack flavor list` dump includes generic project
> flavors (e.g. `shared.*`); without filtering, the recommender may point a
> workflow at a flavor that isn't a valid runner option. Use `--flavor-name-filter`
> (e.g. `^github-runner-`) to restrict the catalog. Malformed entries (non-numeric
> or zero vCPUs/RAM) are dropped automatically.

> **Note on `current_flavor`.** The hostmetrics carry no flavor label, so the selected flavor
> is inferred by reverse-mapping the measured resource shape (`system_cpu_logical_count` →
> vCPUs, total `system_memory_usage_bytes` → RAM) onto the `--flavors` catalog: vCPUs match
> exactly, and since the OS reports slightly less than the advertised RAM, the same-vCPU flavor
> with the nearest advertised RAM is chosen. If two catalog flavors share the same vCPU/RAM
> shape this is ambiguous, and without a `--flavors` catalog the column is `N/A` (read the raw
> `prov_cores` / `prov_ram_gb` instead).
