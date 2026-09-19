from __future__ import annotations

import os
import subprocess
import sys

import click

from repo_policy.apply import apply_all, prune_rulesets
from repo_policy.audit import audit_all
from repo_policy.config import ConfigError, load_policy
from repo_policy.github_client import GitHubAPIError, GitHubClient
from repo_policy.render import render_plan

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_CONFIG_ERROR = 2
EXIT_API_ERROR = 3


def _resolve_token(token: str | None) -> str:
    return token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def _resolve_repo(repo: str | None) -> str:
    if repo:
        return repo
    env_repo = os.environ.get("GITHUB_REPOSITORY")
    if env_repo:
        return env_repo
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=False
    )
    url = result.stdout.strip()
    if url.endswith(".git"):
        url = url[: -len(".git")]
    for separator in ("github.com:", "github.com/"):
        if separator in url:
            return url.split(separator, 1)[1]
    raise click.ClickException("could not determine repository; pass --repo owner/name")


@click.group()
def main() -> None:
    """repo-policy: declarative GitHub repository governance."""


@main.command()
@click.option("--config", "config_path", default="policy.yml", show_default=True)
def validate(config_path: str) -> None:
    try:
        load_policy(config_path)
    except ConfigError as exc:
        click.echo(str(exc), err=True)
        sys.exit(EXIT_CONFIG_ERROR)
    click.echo(f"{config_path} is valid.")
    sys.exit(EXIT_OK)


def _run_check(config_path: str, repo: str | None, token: str | None, *, render: bool) -> int:
    try:
        config = load_policy(config_path)
    except ConfigError as exc:
        click.echo(str(exc), err=True)
        return EXIT_CONFIG_ERROR

    resolved_repo = _resolve_repo(repo)
    owner, name = resolved_repo.split("/", 1)

    try:
        with GitHubClient(token=_resolve_token(token), owner=owner, repo=name) as client:
            results = audit_all(client, config)
    except GitHubAPIError as exc:
        click.echo(str(exc), err=True)
        return EXIT_API_ERROR

    any_drift = False
    for result in results:
        if render:
            click.echo(render_plan(resolved_repo, result.branch, result.changes))
        elif not result.compliant:
            click.echo(f"{result.branch}: {len(result.changes)} change(s) required")
        any_drift = any_drift or not result.compliant

    if not any_drift and not render:
        click.echo(f"{resolved_repo} is compliant.")
    return EXIT_DRIFT if any_drift else EXIT_OK


@main.command()
@click.option("--config", "config_path", default="policy.yml", show_default=True)
@click.option("--repo", default=None)
@click.option("--token", default=None)
def audit(config_path: str, repo: str | None, token: str | None) -> None:
    sys.exit(_run_check(config_path, repo, token, render=False))


@main.command()
@click.option("--config", "config_path", default="policy.yml", show_default=True)
@click.option("--repo", default=None)
@click.option("--token", default=None)
def plan(config_path: str, repo: str | None, token: str | None) -> None:
    sys.exit(_run_check(config_path, repo, token, render=True))


@main.command()
@click.option("--config", "config_path", default="policy.yml", show_default=True)
@click.option("--repo", default=None)
@click.option("--token", default=None)
def apply(config_path: str, repo: str | None, token: str | None) -> None:
    try:
        config = load_policy(config_path)
    except ConfigError as exc:
        click.echo(str(exc), err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    resolved_repo = _resolve_repo(repo)
    owner, name = resolved_repo.split("/", 1)

    try:
        with GitHubClient(token=_resolve_token(token), owner=owner, repo=name) as client:
            results = apply_all(client, config)
            if config.strict:
                for deleted_name in prune_rulesets(client, config):
                    click.echo(f"- removed orphaned ruleset {deleted_name}")
    except GitHubAPIError as exc:
        click.echo(str(exc), err=True)
        sys.exit(EXIT_API_ERROR)

    for result in results:
        if result.applied:
            click.echo(f"{result.branch}: applied {len(result.changes)} change(s)")
        else:
            click.echo(f"{result.branch}: no changes needed")
    sys.exit(EXIT_OK)
