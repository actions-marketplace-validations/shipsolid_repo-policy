from __future__ import annotations

from dataclasses import dataclass

from repo_policy.diff import Change, diff, resolve_desired
from repo_policy.github_client import GitHubClient
from repo_policy.models import BranchPolicy, PolicyConfig, effective_strict
from repo_policy.policies import branch_protection, rulesets


@dataclass
class BranchResult:
    branch: str
    changes: list[Change]
    applied: bool


def prefetch_rulesets(
    client: GitHubClient, config: PolicyConfig, *, force: bool = False
) -> list[dict] | None:
    """Fetch the repo's full ruleset list once per orchestration call (apply_all/audit_all/
    prune_rulesets), instead of each ruleset-enforced branch independently re-fetching it via
    find_ruleset_by_name. Returns None (skip the fetch) unless a branch actually needs it, or
    `force=True` (prune_rulesets always needs the full list, even if no *current* branch is
    ruleset-enforced — an orphan can come from a branch removed from policy.yml entirely)."""
    needs_it = force or any(b.enforcement == "ruleset" for b in config.branches.values())
    return client.list_rulesets() if needs_it else None


def fetch_current(
    client: GitHubClient, branch: str, enforcement: str, *, rulesets_cache: list[dict] | None = None
) -> tuple[BranchPolicy, dict | None, int | None]:
    if enforcement == "branch_protection":
        raw = client.get_branch_protection(branch)
        signed = client.get_required_signatures(branch)
        return branch_protection.from_api(raw, signed_commits=signed), raw, None
    raw = client.find_ruleset_by_name(rulesets.ruleset_name(branch), rulesets=rulesets_cache)
    ruleset_id = raw["id"] if raw else None
    return rulesets.from_api(raw), raw, ruleset_id


def plan_branch(
    client: GitHubClient, config: PolicyConfig, branch: str, *, rulesets_cache: list[dict] | None = None
) -> tuple[list[Change], BranchPolicy]:
    desired = config.branches[branch]
    current, _raw, _ruleset_id = fetch_current(
        client, branch, desired.enforcement, rulesets_cache=rulesets_cache
    )
    resolved = resolve_desired(desired, current, strict=effective_strict(config, branch))
    return diff(resolved, current), resolved


def apply_branch(
    client: GitHubClient, config: PolicyConfig, branch: str, *, rulesets_cache: list[dict] | None = None
) -> BranchResult:
    desired = config.branches[branch]
    current, raw, ruleset_id = fetch_current(
        client, branch, desired.enforcement, rulesets_cache=rulesets_cache
    )
    resolved = resolve_desired(desired, current, strict=effective_strict(config, branch))
    changes = diff(resolved, current)

    if not changes:
        return BranchResult(branch=branch, changes=[], applied=False)

    if desired.enforcement == "branch_protection":
        payload = branch_protection.to_api_payload(resolved, raw)
        client.put_branch_protection(branch, payload)
        if resolved.signed_commits != current.signed_commits:
            client.set_required_signatures(branch, bool(resolved.signed_commits))
    else:
        payload = rulesets.to_api_payload(branch, resolved)
        if ruleset_id is None:
            client.create_ruleset(payload)
        else:
            client.update_ruleset(ruleset_id, payload)

    return BranchResult(branch=branch, changes=changes, applied=True)


def apply_all(
    client: GitHubClient, config: PolicyConfig, *, rulesets_cache: list[dict] | None = None
) -> list[BranchResult]:
    if rulesets_cache is None:
        rulesets_cache = prefetch_rulesets(client, config)
    return [
        apply_branch(client, config, branch, rulesets_cache=rulesets_cache) for branch in config.branches
    ]


def prune_rulesets(
    client: GitHubClient, config: PolicyConfig, *, rulesets_cache: list[dict] | None = None
) -> list[str]:
    """Strict-mode only, gated by the top-level `strict` default (a removed branch has no
    per-branch setting left to consult). Deletes only rulesets matching the `repo-policy:` naming
    convention whose branch is no longer declared — never touches anything else."""
    declared_names = {rulesets.ruleset_name(branch) for branch in config.branches}
    all_rulesets = rulesets_cache if rulesets_cache is not None else client.list_rulesets()
    deleted: list[str] = []
    for summary in all_rulesets:
        name = summary["name"]
        if name.startswith("repo-policy:") and name not in declared_names:
            client.delete_ruleset(summary["id"])
            deleted.append(name)
    return deleted
