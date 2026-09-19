from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class PullRequestPolicy(BaseModel):
    required: bool = True
    approvals: int = 1
    code_owner_review: bool = False


class StatusChecksPolicy(BaseModel):
    required: list[str] = Field(default_factory=list)


class BranchPolicy(BaseModel):
    enforcement: Literal["branch_protection", "ruleset"] = "branch_protection"
    strict: Optional[bool] = None
    pull_requests: Optional[PullRequestPolicy] = None
    status_checks: Optional[StatusChecksPolicy] = None
    signed_commits: Optional[bool] = None
    linear_history: Optional[bool] = None
    allow_force_push: Optional[bool] = None
    allow_deletion: Optional[bool] = None


class PolicyConfig(BaseModel):
    version: int
    strict: bool = False
    branches: dict[str, BranchPolicy]

    @field_validator("version")
    @classmethod
    def _version_must_be_supported(cls, value: int) -> int:
        if value != 1:
            raise ValueError(f"unsupported policy version: {value} (only version 1 is supported)")
        return value


def effective_strict(config: PolicyConfig, branch: str) -> bool:
    """A branch's own `strict` always wins; otherwise inherit the top-level default."""
    branch_policy = config.branches[branch]
    return branch_policy.strict if branch_policy.strict is not None else config.strict
