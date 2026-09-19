from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from repo_policy.models import PolicyConfig


class ConfigError(Exception):
    """Raised when policy.yml is missing, malformed, or fails schema validation."""


class _StrictBoolLoader(yaml.SafeLoader):
    """SafeLoader without YAML 1.1's yes/no/on/off boolean words -- only true/false (any casing)
    resolve as booleans. PyYAML's default bool resolver also treats yes/no/on/off as booleans
    (confirmed: `yaml.safe_load("no")` returns `False`), which would silently turn a branch name
    or status-check context like "no" or "on" into a Python bool before pydantic ever validates
    it. Removing only the bool resolver's y/Y/n/N/o/O entries leaves every other SafeLoader
    behavior, including true/false, untouched -- still exactly as safe as SafeLoader itself."""


_StrictBoolLoader.yaml_implicit_resolvers = {
    first_char: [
        (tag, regexp)
        for tag, regexp in resolvers
        if not (tag == "tag:yaml.org,2002:bool" and first_char in "yYnNoO")
    ]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_policy(path: str | Path) -> PolicyConfig:
    file_path = Path(path)

    if not file_path.exists():
        raise ConfigError(f"policy file not found: {file_path}")

    try:
        raw_text = file_path.read_text()
    except OSError as exc:
        raise ConfigError(f"could not read policy file {file_path}: {exc}") from exc

    try:
        data = yaml.load(raw_text, Loader=_StrictBoolLoader)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {file_path}: {exc}") from exc

    if data is None:
        raise ConfigError(f"policy file is empty: {file_path}")

    try:
        return PolicyConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(file_path, exc)) from exc


def _format_validation_error(path: Path, exc: ValidationError) -> str:
    lines = [f"invalid policy config in {path}:"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "<policy file root>"
        lines.append(f"  - {location}: {error['msg']}")
    return "\n".join(lines)
