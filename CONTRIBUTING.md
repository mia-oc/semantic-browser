# Contributing

Thanks for contributing to Semantic Browser.

## Development setup

```bash
pip install -e ".[full]"
semantic-browser install-browser
```

## Local quality checks

```bash
ruff check src tests --select F,B
mypy src
pytest tests/unit tests/e2e
```

## Pull request expectations

- Keep changes focused and well-scoped.
- Add or update tests for behavior changes.
- Update docs when user-facing behavior changes.
- Do not commit secrets or local trace artifacts.
