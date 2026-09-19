from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from repo_policy.models import PolicyConfig


class ConfigError(Exception):
    """Raised when policy.yml is missing, malformed, or fails schema validation."""


def load_policy(path: str | Path) -> PolicyConfig:
    file_path = Path(path)

    if not file_path.exists():
        raise ConfigError(f"policy file not found: {file_path}")

    try:
        raw_text = file_path.read_text()
    except OSError as exc:
        raise ConfigError(f"could not read policy file {file_path}: {exc}") from exc

    try:
        data = yaml.safe_load(raw_text)
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
        location = ".".join(str(part) for part in error["loc"])
        lines.append(f"  - {location}: {error['msg']}")
    return "\n".join(lines)
