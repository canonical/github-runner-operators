(hotfix_and_rollback_charm_releases)=

# How to hotfix or roll back a charm release

This guide covers two manual paths outside the normal edge-to-candidate-to-stable
pipeline described in {ref}`release_process`: releasing a hotfix straight to
`latest/candidate`, and rolling back a release that has already reached
candidate or production.

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

Then take the same revisions to production through the normal production
promotion process. The hotfix still follows the production gate; only the
candidate release is done by hand.

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

Then revert the production pin to the earlier revision through the normal
production promotion process.

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
2. Roll back the production pin.
3. Run `juju resolved` on any units in error.
4. Release the older revisions back to candidate, both charms together:

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
