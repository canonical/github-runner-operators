#!/usr/bin/env python3
# Extracted from https://github.com/canonical/github-runner-webhook-router
# Standalone script — only requires PyGithub (`pip install PyGithub`).
#
# Auth via environment variables (mutually exclusive):
#   Token auth:  GITHUB_TOKEN
#   App auth:    GITHUB_APP_CLIENT_ID, GITHUB_APP_INSTALLATION_ID, GITHUB_APP_PRIVATE_KEY
#
# Env file support: if a .env file exists next to this script it is loaded automatically
# (one VAR=value per line). chmod 600 your .env file to keep secrets safe.
#
# Usage:
#   python3 redeliver_webhooks.py --since 3600 --github-path canonical --webhook-id 123456
#   python3 redeliver_webhooks.py --since 7200 --github-path canonical/my-repo --webhook-id 789

import argparse
import csv
import json
import logging
import os
import sys
from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Callable, Iterator, ParamSpec, TypeVar

from github import BadCredentialsException, Github, GithubException, RateLimitExceededException
from github.Auth import AppAuth, AppInstallationAuth, Token

SUPPORTED_GITHUB_EVENT = "workflow_job"
REDELIVERABLE_ACTIONS = {"queued", "completed"}

ARG_PARSE_ERROR_EXIT_CODE = 1
REDELIVERY_ERROR_EXIT_CODE = 2

GITHUB_TOKEN_ENV_NAME = "GITHUB_TOKEN"
GITHUB_APP_CLIENT_ID_ENV_NAME = "GITHUB_APP_CLIENT_ID"
GITHUB_APP_INSTALLATION_ID_ENV_NAME = "GITHUB_APP_INSTALLATION_ID"
GITHUB_APP_PRIVATE_KEY_ENV_NAME = "GITHUB_APP_PRIVATE_KEY"

OK_STATUS = "OK"

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)


@dataclass
class GithubAppAuthDetails:
    """Authentication details for GitHub App auth."""

    client_id: str
    installation_id: int
    private_key: str


GithubToken = str
GithubAuthDetails = GithubAppAuthDetails | GithubToken

_ParsedArgs = namedtuple(
    "_ParsedArgs", ["since", "github_auth_details", "webhook_address", "metrics_file"]
)


@dataclass
class WebhookAddress:
    """Identifies the webhook to check deliveries for."""

    github_org: str
    github_repo: str | None
    id: int


@dataclass
class _WebhookDeliveryAttempt:
    id: int
    status: str
    delivered_at: datetime
    action: str | None
    event: str


@dataclass
class _DeliveryStats:
    total_checked: int
    redelivered: int


class RedeliveryError(Exception):
    """Raised when an error occurs during redelivery."""


class ArgParseError(Exception):
    """Raised when an error occurs during argument parsing."""


def _load_env_file() -> None:
    """Load a .env file next to this script if it exists."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.is_file():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            if key and _ == "=":
                os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    """Run the module as script."""
    _load_env_file()
    args = _arg_parsing()

    stats = _redeliver_failed_webhook_delivery_attempts(
        github_auth=args.github_auth_details,
        webhook_address=args.webhook_address,
        since_seconds=args.since,
    )

    print(json.dumps({"total_checked": stats.total_checked, "redelivered": stats.redelivered}))

    if args.metrics_file:
        _append_metrics_csv(
            path=args.metrics_file,
            since_seconds=args.since,
            stats=stats,
        )


def _arg_parsing() -> _ParsedArgs:
    """Parse command line arguments and environment-based auth details.

    Raises:
        ArgParseError: If the arguments are invalid.
    """
    parser = argparse.ArgumentParser(
        description="Redeliver failed GitHub webhook deliveries (workflow_job events)."
    )
    parser.add_argument(
        "--since",
        type=int,
        help="Seconds to look back for failed deliveries.",
        required=True,
    )
    parser.add_argument(
        "--github-path",
        type=str,
        help="Organisation or org/repo path (e.g. canonical or canonical/my-repo).",
        required=True,
    )
    parser.add_argument(
        "--webhook-id",
        type=int,
        help="The webhook ID to check deliveries for.",
        required=True,
    )
    parser.add_argument(
        "--metrics-file",
        type=Path,
        help="Path to a CSV file to append per-run metrics to (created with header if absent).",
        required=False,
        default=None,
    )
    args = parser.parse_args()

    github_app_client_id = os.getenv(GITHUB_APP_CLIENT_ID_ENV_NAME)
    github_app_installation_id = os.getenv(GITHUB_APP_INSTALLATION_ID_ENV_NAME)
    github_app_private_key = os.getenv(GITHUB_APP_PRIVATE_KEY_ENV_NAME)
    github_token = os.getenv(GITHUB_TOKEN_ENV_NAME)

    github_auth_details: GithubAuthDetails
    got_str = (
        f" Got {GITHUB_APP_CLIENT_ID_ENV_NAME}={github_app_client_id},"
        f" {GITHUB_APP_INSTALLATION_ID_ENV_NAME}={github_app_installation_id},"
        f" {GITHUB_APP_PRIVATE_KEY_ENV_NAME}={'***' if github_app_private_key else None},"
        f" {GITHUB_TOKEN_ENV_NAME}={'***' if github_token else None}"
    )
    if github_token and (
        github_app_client_id or github_app_installation_id or github_app_private_key
    ):
        raise ArgParseError(
            "GitHub auth specified in two ways. "
            "Use either GITHUB_TOKEN or the app auth variables, not both."
            f"{got_str}"
        )
    if github_token:
        github_auth_details = github_token
    elif github_app_client_id and github_app_installation_id and github_app_private_key:
        try:
            github_auth_details = GithubAppAuthDetails(
                client_id=github_app_client_id,
                installation_id=int(github_app_installation_id),
                private_key=github_app_private_key,
            )
        except ValueError as exc:
            raise ArgParseError(f"Failed to parse GitHub auth details: {exc}") from exc
    else:
        raise ArgParseError(
            "GitHub auth details incomplete. "
            "Set GITHUB_TOKEN or all three app auth variables."
            f"{got_str}"
        )

    webhook_address = WebhookAddress(
        github_org=args.github_path.split("/")[0],
        github_repo=args.github_path.split("/")[1] if "/" in args.github_path else None,
        id=args.webhook_id,
    )

    return _ParsedArgs(
        since=args.since,
        github_auth_details=github_auth_details,
        webhook_address=webhook_address,
        metrics_file=args.metrics_file,
    )


def _github_api_exc_decorator(func: Callable[P, R]) -> Callable[P, R]:
    """Decorator to handle GitHub API exceptions."""

    @wraps(func)
    def _wrapper(*posargs: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*posargs, **kwargs)
        except BadCredentialsException as exc:
            raise RedeliveryError(
                "Bad credentials — check that your token/app credentials are valid "
                "and have the required permissions."
            ) from exc
        except RateLimitExceededException as exc:
            raise RedeliveryError(
                "GitHub rate limit exceeded — wait before retrying."
            ) from exc
        except GithubException as exc:
            raise RedeliveryError(f"GitHub API error: {exc}") from exc

    return _wrapper


@_github_api_exc_decorator
def _redeliver_failed_webhook_delivery_attempts(
    github_auth: GithubAuthDetails, webhook_address: WebhookAddress, since_seconds: int
) -> _DeliveryStats:
    """Redeliver failed webhook deliveries since a certain number of seconds ago."""
    github = _get_github_client(github_auth)

    deliveries = _iter_delivery_attempts(github_client=github, webhook_address=webhook_address)
    since_datetime = datetime.now(tz=timezone.utc) - timedelta(seconds=since_seconds)
    failed_deliveries, total_checked = _collect_failed_attempts_since(
        deliveries=deliveries, since_datetime=since_datetime
    )
    redelivered = _redeliver_attempts(
        deliveries=iter(failed_deliveries), github_client=github, webhook_address=webhook_address
    )
    return _DeliveryStats(total_checked=total_checked, redelivered=len(failed_deliveries))


def _get_github_client(github_auth: GithubAuthDetails) -> Github:
    if isinstance(github_auth, GithubToken):
        return Github(auth=Token(github_auth))

    app_auth = AppAuth(app_id=github_auth.client_id, private_key=github_auth.private_key)
    app_installation_auth = AppInstallationAuth(
        app_auth=app_auth, installation_id=github_auth.installation_id
    )
    return Github(auth=app_installation_auth)


def _iter_delivery_attempts(
    github_client: Github, webhook_address: WebhookAddress
) -> Iterator[_WebhookDeliveryAttempt]:
    webhook_origin = (
        github_client.get_repo(f"{webhook_address.github_org}/{webhook_address.github_repo}")
        if webhook_address.github_repo
        else github_client.get_organization(webhook_address.github_org)
    )
    deliveries = webhook_origin.get_hook_deliveries(webhook_address.id)
    for delivery in deliveries:
        required_fields = {"id", "status", "delivered_at", "event"}
        none_fields = {
            field for field in required_fields if getattr(delivery, field, None) is None
        }
        if none_fields:
            raise AssertionError(
                f"Webhook delivery {delivery.raw_data} missing required fields: {none_fields}"
            )
        yield _WebhookDeliveryAttempt(
            id=delivery.id,
            status=delivery.status,
            delivered_at=delivery.delivered_at,
            action=delivery.action,
            event=delivery.event,
        )


def _collect_failed_attempts_since(
    deliveries: Iterator[_WebhookDeliveryAttempt], since_datetime: datetime
) -> tuple[list[_WebhookDeliveryAttempt], int]:
    """Return (failed_deliveries, total_checked) for deliveries within the time window."""
    failed = []
    total = 0
    for delivery in deliveries:
        if delivery.delivered_at < since_datetime:
            break
        total += 1
        if (
            delivery.status != OK_STATUS
            and delivery.action in REDELIVERABLE_ACTIONS
            and delivery.event == SUPPORTED_GITHUB_EVENT
        ):
            failed.append(delivery)
    return failed, total


def _redeliver_attempts(
    deliveries: Iterator[_WebhookDeliveryAttempt],
    github_client: Github,
    webhook_address: WebhookAddress,
) -> int:
    count = 0
    for delivery in deliveries:
        path_base = (
            f"/repos/{webhook_address.github_org}/{webhook_address.github_repo}"
            if webhook_address.github_repo
            else f"/orgs/{webhook_address.github_org}"
        )
        url = f"{path_base}/hooks/{webhook_address.id}/deliveries/{delivery.id}/attempts"
        github_client.requester.requestJsonAndCheck("POST", url)
        count += 1
    return count


def _append_metrics_csv(
    path: Path,
    since_seconds: int,
    stats: _DeliveryStats,
) -> None:
    """Append one metrics row to a CSV file, creating it with a header if absent."""
    fieldnames = ["timestamp", "since_seconds", "total_checked", "redelivered"]
    write_header = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "since_seconds": since_seconds,
            "total_checked": stats.total_checked,
            "redelivered": stats.redelivered,
        })


if __name__ == "__main__":
    try:
        main()
    except ArgParseError as exc:
        print(f"{exc}", file=sys.stderr)
        sys.exit(ARG_PARSE_ERROR_EXIT_CODE)
    except RedeliveryError as exc:
        logger.exception("Webhook redelivery failed: %s", exc)
        sys.exit(REDELIVERY_ERROR_EXIT_CODE)
