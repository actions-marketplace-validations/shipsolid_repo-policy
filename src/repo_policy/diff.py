from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from repo_policy.models import BranchPolicy, PullRequestPolicy

ChangeAction = Literal["add", "modify", "remove"]

_FIELDS = (
    "pull_requests",
    "status_checks",
    "signed_commits",
    "linear_history",
    "allow_force_push",
    "allow_deletion",
)

_SCHEMA_DEFAULTS: dict[str, Any] = {
    "pull_requests": PullRequestPolicy(required=False, approvals=0, code_owner_review=False),
    # None, not StatusChecksPolicy(required=[]): branch_protection.from_api / rulesets.from_api
    # both represent "no status checks configured" as None. The strict default must match that
    # exact representation, or a fully-compliant permissive branch shows permanent phantom drift.
    "status_checks": None,
    "signed_commits": False,
    "linear_history": False,
    "allow_force_push": True,
    "allow_deletion": True,
}

# allow_force_push/allow_deletion have inverted polarity vs. every other field: False means a
# restriction IS present (force push blocked), True means no restriction — the opposite of
# fields like linear_history, where False/empty means no rule exists.
_INVERTED_FIELDS = {"allow_force_push", "allow_deletion"}


@dataclass(frozen=True)
class Change:
    field: str
    current_value: Any
    desired_value: Any
    action: ChangeAction


def resolve_desired(desired: BranchPolicy, current: BranchPolicy, *, strict: bool) -> BranchPolicy:
    """Fill in every undeclared (None) field: from `current` in managed-scope mode, or from the
    permissive schema default in strict mode. The result always has every field concretely set,
    so `diff()` never has to special-case None."""
    resolved: dict[str, Any] = {}
    for field in _FIELDS:
        value = getattr(desired, field)
        if value is not None:
            resolved[field] = value
        elif strict:
            resolved[field] = _SCHEMA_DEFAULTS[field]
        else:
            resolved[field] = getattr(current, field)
    return desired.model_copy(update=resolved)


def diff(desired: BranchPolicy, current: BranchPolicy) -> list[Change]:
    changes: list[Change] = []
    for field in _FIELDS:
        desired_value = getattr(desired, field)
        current_value = getattr(current, field)
        if desired_value == current_value:
            continue
        changes.append(
            Change(
                field=field,
                current_value=current_value,
                desired_value=desired_value,
                action=_classify_action(field, current_value, desired_value),
            )
        )
    return changes


def _classify_action(field: str, current_value: Any, desired_value: Any) -> ChangeAction:
    if _is_empty(field, current_value):
        return "add"
    if _is_empty(field, desired_value):
        return "remove"
    return "modify"


def _is_empty(field: str, value: Any) -> bool:
    if field in _INVERTED_FIELDS:
        return value is True or value is None
    if value is None or value is False:
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    if hasattr(value, "required"):
        required = value.required
        return required is False if isinstance(required, bool) else len(required) == 0
    return False
