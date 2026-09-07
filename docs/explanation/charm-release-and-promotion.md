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
`garm` and `garm-configurator`. They always move together, because the
configurator supplies GARM's scale-set configuration: a revision of one is only
ever validated against the revision of the other it was tested with, and the
end-to-end test exercises the pair.

Charmhub has no way to release two charms in one transaction, so the workflow
releases them one after the other — `garm`, with the `app-image` resource
revision that was attached to the tested edge revision, then
`garm-configurator`. If the second release fails, the first has already
happened: `latest/candidate` then holds a mismatched pair. The workflow says so
in its run summary, naming what it already released, because the repair is
manual. Either release the missing charm's tested revision to candidate:

```bash
charmcraft release garm-configurator --revision=<n> --channel=latest/candidate
```

or put the charm that did get released back to the revision candidate held
before the run, following {ref}`rollbacks` below. Do not leave the pair
mismatched: production pins candidate, so an untested combination is what the
next Terraform bump would ship.

Production does not follow candidate automatically. Instead, the internal
GitOps Terraform repository pins production to a specific candidate revision.
Renovate opens a revision-bump pull request when a newer candidate is available,
covering both charms in one pull request so the pair stays together. Renovate is
deliberately configured not to merge that pull request on its own. A human must
approve and merge it, then apply the Terraform change. That approval is the
production gate.

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

## The `charmhub-stable` environment

The stable gate needs one piece of repository configuration: a GitHub
Environment named `charmhub-stable` with required reviewers. It already exists.
The environment carries no secrets of its own — the weekly workflow
authenticates to Charmhub with the repository-level `CHARMHUB_TOKEN` secret, the
same one the other release workflows use. The environment is there for the
approval, not for the credentials.

A missing environment would not fail an approval on its own — GitHub treats
`environment:` pointing at nothing as a no-op and runs the job straight through.
The weekly workflow therefore checks first: its `verify-environment` job queries
the environment and fails the run if it is absent or has no required-reviewers
rule. The stable gate cannot silently disappear; an environment without
required reviewers stops the release instead of waving it through.

## Hotfixes

Building a charm locally does not create a Charmhub revision — `charmcraft
release` only moves a revision that already exists. So a hotfix is upload, then
release.

Pack the charm from the fix pull request, then upload it. The upload prints the
revision number to release:

```bash
charmcraft upload <charm>.charm
```

For `garm`, the charm is packaged with an `app-image` OCI resource, and a
release that does not name a resource revision is rejected. Either reuse the
resource revision already attached to the revision you are replacing, which
`charmcraft status garm` reports alongside each release, or upload a new image
and use the revision that returns:

```bash
charmcraft upload-resource garm app-image --image=<image-digest>
```

Then release the charm revision to candidate, passing the resource revision for
`garm` exactly as the daily workflow does:

```bash
charmcraft release garm --revision=<n> --channel=latest/candidate \
  --resource=app-image:<r>
charmcraft release garm-configurator --revision=<n> --channel=latest/candidate
```

Release both charms if the fix changes the pair, so candidate does not end up
holding a combination that was never tested together.

Then take the same revisions to production through the normal Terraform pin in
the internal GitOps repository. The hotfix still follows the production gate;
only the candidate release is done by hand.

For the full set of upload and release options, see the Charmcraft guides on
[managing revisions](https://documentation.ubuntu.com/charmcraft/en/stable/howto/manage-revisions/)
and the [`release` command](https://documentation.ubuntu.com/charmcraft/latest/reference/commands/release/).

(rollbacks)=

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
5. Release the older revisions back to candidate, both charms together:

   ```bash
   charmcraft release garm --revision=<n> --channel=latest/candidate \
     --resource=app-image:<r>
   charmcraft release garm-configurator --revision=<n> --channel=latest/candidate
   ```

Leave the daily workflow disabled until promoting the current edge revision is
acceptable. Waiting for the rollback to "settle" does not change what the
workflow does: it compares revision numbers, and edge is still ahead of the
revision you rolled candidate back to, so the first successful run after you
re-enable it promotes that newer revision again. Re-enable it once the fix for
whatever caused the rollback has reached edge — or once you are content for the
revision you rolled back from to return to candidate.
