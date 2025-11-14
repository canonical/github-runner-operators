# Branch Protection Configuration

## Overview

This repository uses a robust status check pattern to prevent PRs from being blocked by skipped workflow jobs. All workflows run on every PR, but individual test jobs are conditionally executed based on file changes detected by [dorny/paths-filter](https://github.com/dorny/paths-filter).

## How It Works

Each workflow follows this pattern:

1. **detect-changes job**: Always runs and uses `dorny/paths-filter` to detect which files changed
2. **test jobs**: Only run if relevant files changed (conditional on detect-changes output)
3. **status-check job**: Always runs (with `if: always()`) and reports the final status:
   - ✅ Success if tests were skipped (no relevant changes)
   - ✅ Success if tests ran and passed
   - ❌ Failure if tests ran and failed

## Branch Protection Rules

Configure branch protection to require **only** the following status check contexts:

### Required Status Checks

- `Run Unit and Lint Tests` - from `tests.yaml`
- `integration-status-check` - from `webhook_gateway_tests.yaml`
- `terraform-status-check` - from `test_terraform_webhook_module.yaml`
- `terraform-lint-status-check` - from `lint_terraform_webhook.yaml`

**Important**: Do NOT require the individual test jobs like `integration-test`, `charm-integration-tests`, `test-terraform`, or `validate`. These jobs may be skipped, which would block merging.

## Benefits

1. **No blocked PRs**: Status checks always complete, even when tests are skipped
2. **Efficient CI**: Tests only run when relevant files change
3. **Clear status**: Single status check per workflow makes branch protection simple
4. **Predictable merging**: PRs can always merge if they don't affect certain areas

## Example Workflow Structure

```yaml
jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      my-component: ${{ steps.filter.outputs.my-component }}
    steps:
      - uses: actions/checkout@v5
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            my-component:
              - 'path/to/component/**'

  test:
    needs: detect-changes
    if: needs.detect-changes.outputs.my-component == 'true'
    runs-on: ubuntu-latest
    steps:
      # ... test steps ...

  status-check:
    runs-on: ubuntu-latest
    needs: [detect-changes, test]
    if: always()
    steps:
      - name: Check test results
        run: |
          if [ "${{ needs.detect-changes.outputs.my-component }}" != "true" ]; then
            echo "No changes detected, skipping tests is expected"
            exit 0
          fi

          test_result="${{ needs.test.result }}"
          if [ "$test_result" = "failure" ]; then
            echo "Tests failed"
            exit 1
          fi

          echo "Tests passed"
          exit 0
```

## Configuring Branch Protection

1. Go to Settings → Branches → Branch protection rules
2. Add or edit rule for your main branch (e.g., `main`)
3. Enable "Require status checks to pass before merging"
4. Search for and select the `*-status-check` contexts listed above
5. Save the rule

## Troubleshooting

**Q: My PR is blocked but tests passed**
- Check if you required the individual test jobs instead of the `*-status-check` jobs
- Only the `*-status-check` jobs should be required

**Q: Tests aren't running when I expect them to**
- Check the `detect-changes` job output to see what was detected
- Verify the path filters match your changed files
- Remember: path filters use glob patterns

**Q: The status check failed but I don't see which test failed**
- Look at the `*-status-check` job logs, which show the results of all test jobs
- Then check the individual test job logs for details
