from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from repo_policy.models import PolicyConfig


class ConfigError(Exception):
    """Raised when policy.yml is missing, malformed, or fails schema validation."""


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader without two of YAML 1.1's legacy scalar-resolution surprises: the yes/no/on/off
    boolean words, and octal/sexagesimal integers.

    PyYAML's default bool resolver treats yes/no/on/off as booleans (confirmed:
    `yaml.safe_load("no")` returns `False`), which would silently turn a branch name or
    status-check context like "no" or "on" into a Python bool before pydantic ever validates it.
    Its default int resolver also treats a leading-zero scalar as octal (confirmed:
    `yaml.safe_load("010")` returns `8`, not `10`), which would silently weaken a leading-zero
    approvals count (e.g. from copy/paste alignment or a %02d-formatted generator) instead of
    matching what was typed -- Python 3's own `int("010")` is decimal `10`, and pydantic coerces a
    numeric-looking string the same way, so leaving `010` as a plain string here and letting
    pydantic's int coercion handle it produces the value a human actually expects.

    Removing only the bool resolver's y/Y/n/N/o/O entries and narrowing the int resolver to
    binary/decimal/hex (dropping octal and the obscure base-60 `12:34` form) leaves every other
    SafeLoader behavior, including true/false and 0x/0b-prefixed ints, untouched -- still exactly
    as safe as SafeLoader itself against arbitrary object construction."""


_StrictLoader.yaml_implicit_resolvers = {
    first_char: [
        (tag, regexp)
        for tag, regexp in resolvers
        if not (tag == "tag:yaml.org,2002:bool" and first_char in "yYnNoO")
        and tag != "tag:yaml.org,2002:int"
    ]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_StrictLoader.add_implicit_resolver(
    "tag:yaml.org,2002:int",
    re.compile(r"^(?:[-+]?0b[0-1_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+)$"),
    list("-+0123456789"),
)


def load_policy(path: str | Path) -> PolicyConfig:
    file_path = Path(path)

    if not file_path.exists():
        raise ConfigError(f"policy file not found: {file_path}")

    try:
        raw_text = file_path.read_text()
    except OSError as exc:
        raise ConfigError(f"could not read policy file {file_path}: {exc}") from exc

    try:
        data = yaml.load(raw_text, Loader=_StrictLoader)
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
