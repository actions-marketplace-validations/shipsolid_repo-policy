# Contributing

## Prerequisites

- Python 3.10+
- No other runtime dependency — the test suite mocks every GitHub API call (`respx`); you do not
  need a real GitHub token to develop or run tests.
- `docker` only if you're changing `Dockerfile`/`action.yml` and want to build the Action image
  locally.

## Setup

```bash
pip install -e ".[dev]"
```

## Repository Structure

```
src/repo_policy/       the package — see ARCHITECTURE.md for what each module owns
tests/                 one test file per source module, plus test_idempotency.py and
                       test_policies_parity.py (cross-cutting regression guards)
docs/adrs/             why key decisions were made
docs/ci-cd.md          release pipeline
docs/test-strategy.md  what's tested and why
docs/troubleshooting.md
action.yml, Dockerfile the GitHub Action
.github/workflows/     ci.yml (lint/typecheck/test), release.yml (semantic-release + PyPI)
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
