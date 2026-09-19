# Contributing

## Setup

```bash
pip install -e ".[dev]"
```

## Before opening a PR

```bash
ruff check src tests
mypy src
pytest -v
```

## Commit messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/) — releases and
version bumps are automated by `python-semantic-release` from commit history:

- `feat: ...` → minor version bump
- `fix: ...` → patch version bump
- `feat!: ...` or a `BREAKING CHANGE:` footer → major version bump
- `chore:`, `docs:`, `test:`, `ci:` → no release

## Adding a new policy field

1. Add the field to the relevant model in `src/repo_policy/models.py`.
2. Add it to `_FIELDS` and `_SCHEMA_DEFAULTS` in `src/repo_policy/diff.py`.
3. Map it to both backends in `src/repo_policy/policies/branch_protection.py` and
   `src/repo_policy/policies/rulesets.py`.
4. Add the label to `_LABELS` in `src/repo_policy/render.py`.
5. Add coverage in each affected test file — the diff engine, both translators, and the
   idempotency test in `tests/test_idempotency.py`.
