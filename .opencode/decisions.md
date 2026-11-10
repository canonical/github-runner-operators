# Houston decisions

<!-- foreman:meta
{
  "version": 1,
  "nextQuestion": 1,
  "nextDecision": 5,
  "questions": [],
  "decisions": [
    {
      "id": "D-001",
      "decidedAt": "2026-11-09T14:40:49.864Z",
      "text": "ISD-7499 is implemented as the relation-data refactor only: LXD provider config options/behaviour are left out because the ticket says it is only a refactoring task and must not touch charm logic."
    },
    {
      "id": "D-002",
      "decidedAt": "2026-11-09T23:02:31.956Z",
      "text": "Review feedback: garm-configurator now builds with the uv plugin and consumes the shared garm-configurator-relation package via [tool.uv.sources]. garm keeps the go-framework extension (ubuntu@24.04), which owns the charm part and only supports the legacy charm plugin, so it lists the shared package in requirements.txt instead; no dump part remains."
    },
    {
      "id": "D-003",
      "decidedAt": "2026-11-10T16:22:26.566Z",
      "text": "CI fix: garm could not build with ../lib in requirements.txt because the go-framework charm part installs requirements in a directory where the monorepo parent is not reachable. garm now copies the shared module into lib/ with an explicit nil-plugin part (source ../lib, override-build install), while garm-configurator keeps the uv plugin and [tool.uv.sources]. Both charms pack successfully under CHARMCRAFT_EXPERIMENTAL_MONOREPO=1."
    },
    {
      "id": "D-004",
      "decidedAt": "2026-11-10T17:16:26.534Z",
      "text": "Reverted the cross-charm monorepo design: the pydantic ProviderConfig model and tolerant decoder now live in charms/garm-configurator/lib (with its pyproject for a future git dependency). garm-configurator writes the provider payload with ops.Relation.save; garm and the shared charms/lib are untouched, so the follow-up child PR will add the reader."
    }
  ]
}
-->

## Open questions

_None._

## Answered questions

_None._

## Settled decisions

### D-001

ISD-7499 is implemented as the relation-data refactor only: LXD provider config options/behaviour are left out because the ticket says it is only a refactoring task and must not touch charm logic.

### D-002

Review feedback: garm-configurator now builds with the uv plugin and consumes the shared garm-configurator-relation package via [tool.uv.sources]. garm keeps the go-framework extension (ubuntu@24.04), which owns the charm part and only supports the legacy charm plugin, so it lists the shared package in requirements.txt instead; no dump part remains.

### D-003

CI fix: garm could not build with ../lib in requirements.txt because the go-framework charm part installs requirements in a directory where the monorepo parent is not reachable. garm now copies the shared module into lib/ with an explicit nil-plugin part (source ../lib, override-build install), while garm-configurator keeps the uv plugin and [tool.uv.sources]. Both charms pack successfully under CHARMCRAFT_EXPERIMENTAL_MONOREPO=1.

### D-004

Reverted the cross-charm monorepo design: the pydantic ProviderConfig model and tolerant decoder now live in charms/garm-configurator/lib (with its pyproject for a future git dependency). garm-configurator writes the provider payload with ops.Relation.save; garm and the shared charms/lib are untouched, so the follow-up child PR will add the reader.
