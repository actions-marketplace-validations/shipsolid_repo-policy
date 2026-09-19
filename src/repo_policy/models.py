from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PullRequestPolicy(BaseModel):
    required: bool = True
    approvals: int = 1
    code_owner_review: bool = False
    dismiss_stale_reviews: bool = False
    require_last_push_approval: bool = False


class StatusChecksPolicy(BaseModel):
    required: list[str] = Field(default_factory=list)


# field name -> its permissive (no-op) value under enforcement: ruleset. rulesets.from_api()
# constructs internal "current state" BranchPolicy objects with these exact values for each field
# below (never None) — the validator below must let that through unrejected, so it only rejects a
# *non-permissive* (actually-restrictive) value, not merely a non-None one. A human writing
# `enforce_admins: false` under `enforcement: ruleset` is a harmless no-op declaration and is
# allowed; `enforce_admins: true` is a real restriction with no ruleset equivalent and is rejected.
_RULESET_UNSUPPORTED_FIELDS: dict[str, bool] = {"enforce_admins": False}


class BranchPolicy(BaseModel):
    enforcement: Literal["branch_protection", "ruleset"] = "branch_protection"
    strict: bool | None = None
    pull_requests: PullRequestPolicy | None = None
    status_checks: StatusChecksPolicy | None = None
    signed_commits: bool | None = None
    linear_history: bool | None = None
    allow_force_push: bool | None = None
    allow_deletion: bool | None = None
    enforce_admins: bool | None = None

    @model_validator(mode="after")
    def _reject_ruleset_unsupported_fields(self) -> "BranchPolicy":
        if self.enforcement != "ruleset":
            return self
        set_fields = [
            name for name, permissive in _RULESET_UNSUPPORTED_FIELDS.items()
            if getattr(self, name) not in (None, permissive)
        ]
        if set_fields:
            raise ValueError(
                f"{', '.join(set_fields)} not supported under enforcement: ruleset "
                "(no GitHub Rulesets equivalent) -- use enforcement: branch_protection, "
                "or remove these fields"
            )
        return self


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
