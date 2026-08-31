---
myst:
  html_meta:
    "description lang=en": "Explain how GitHub runner charms move through edge, candidate, and stable."
---

(release_process)=

# Charm release and promotion process

GitHub runner charm releases move through three Charmhub channels:
`latest/edge`, `latest/candidate`, and `latest/stable`.

The release process is designed to keep the fast path automated while leaving
the two production decisions with a human reviewer:

- whether to take a candidate revision into production, and
- whether a candidate revision has truly soaked in production long enough to
  become stable.

```{mermaid}
flowchart TD
  PUSH[Push to main] --> EDGE[Publish all charms to latest/edge]
  EDGE --> DAILY[Daily edge-to-candidate workflow]
  DAILY -->|edge ahead of candidate| E2E[GARM end-to-end test]
  E2E -->|pass| CAND[Release garm and garm-configurator to latest/candidate]
  CAND --> RENOVATE[Renovate updates the production Terraform pin]
  RENOVATE --> PROD[Human approves and applies the production pin]
  PROD --> WEEKLY[Weekly candidate-to-stable workflow]
  WEEKLY -->|7-day soak, approved| STABLE[Release latest/candidate to latest/stable]
```

## Channel flow

Every push to `main` publishes all charms to `latest/edge` through
`.github/workflows/publish_charms.yml`.

Once a day, `promote_edge_to_candidate.yaml` compares the edge revision with
the candidate revision. If edge is not ahead of candidate, the workflow skips
so the repository does not rerun the expensive end-to-end test for no change.
When edge is ahead, the workflow runs the GARM end-to-end test from
`garm_e2e.yaml` against the published edge revision. If that test passes, the
workflow releases the new revision to `latest/candidate`.

Only two charms move through this automated edge-to-candidate promotion:
`garm` and `garm-configurator`. They always move together, and the workflow
releases them atomically so production never sees a mixed pair.

Production does not follow candidate automatically. Instead, the internal
GitOps Terraform repository pins production to a specific candidate revision.
Renovate opens a revision-bump pull request when a newer candidate is available.
A human must approve and merge that pull request, then apply the Terraform
change. That approval is the production gate.

Once a candidate revision has soaked for seven days, the weekly
`promote_candidate_to_stable.yaml` workflow promotes it to `latest/stable`.
The workflow uses a GitHub Environment named `charmhub-stable` with required
reviewers so a human approves the stable release at the end of the soak window.

## Human review gates

### Renovate pull request gate

This gate decides whether a candidate revision should move into production.
The reviewer checks that the revision is the one they want to run in the live
environment, then merges the revision-bump pull request and applies the
Terraform change.

### `charmhub-stable` environment gate

This gate decides whether a candidate revision is ready to become stable.
The weekly workflow measures soak time using the Charmhub candidate release
timestamp. That timestamp proves when the revision was published to
`latest/candidate`; it does **not** prove that production ran that revision for
the full soak window. The reviewer at this gate must confirm that the revision
really has been running in production for the required time.

That limitation is intentional in the current design, so the approval step is
the place where a human closes the gap between candidate publication and
production promotion.

## One-time repository setup

Create a GitHub Environment named `charmhub-stable` in the repository settings
and configure it with required reviewers.

Also scope `CHARMHUB_TOKEN` to that environment so the weekly promotion
workflow can authenticate to Charmhub.

If the environment does not exist, GitHub treats the approval as a no-op rather
than failing the workflow. That means the stable gate silently disappears until
the environment is created, so make sure the environment exists before you rely
on it.

## Hotfixes

For a hotfix, build the charm from the fix pull request and release it manually
to candidate:

```bash
charmcraft release <charm> --revision=<n> --channel=latest/candidate
```

Then take the same revision to production through the normal Terraform pin in
the internal GitOps repository. The hotfix still follows the production gate;
only the candidate release is done by hand.

## Rollbacks

Rollbacks are manual.

First, clear any Juju units in error:

```bash
juju resolved <application>/<unit>
```

Then revert the production Terraform pin to the earlier revision and apply the
change.

The candidate channel is not rolled back automatically. If you need candidate
to point at an older revision, you must update it separately.

```{warning}
Before you point `latest/candidate` back at an older revision, disable
`promote_edge_to_candidate.yaml` first. Otherwise the next daily run sees edge
ahead of candidate and immediately repromotes the newer revision over your
rollback.
```

The rollback sequence therefore becomes:

1. Disable the daily edge-to-candidate workflow.
2. Roll back the production Terraform pin.
3. Run `juju resolved` on any units in error.
4. Apply the Terraform change.

When the older revision should stay on candidate again, re-enable the daily
workflow after you are satisfied that the rollback has settled.
