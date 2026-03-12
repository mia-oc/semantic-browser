# Publishing (PyPI)

This project is structured for Python package publishing via `pyproject.toml`.

## 1. Prerequisites

- PyPI account (and optionally TestPyPI account)
- Trusted publishing setup or API token
- Clean git working tree
- Passing checks (`ruff`, `mypy`, tests)

## 2. Build artifacts

```bash
python -m pip install --upgrade build twine
python -m build
```

This creates:

- `dist/*.whl`
- `dist/*.tar.gz`

## 3. Verify package metadata

```bash
python -m twine check dist/*
```

## 4. Publish

TestPyPI first (recommended):

```bash
python -m twine upload --repository testpypi dist/*
```

PyPI:

```bash
python -m twine upload dist/*
```

## 5. Post-publish validation

```bash
pip install semantic-browser==<version>
semantic-browser version
```

## Release checklist

1. Update version (`pyproject.toml`) using `tools/next_version.py` rule.
2. Update `CHANGELOG.md`.
3. Ensure README release line matches version/tag.
4. Tag release in git.
5. Build and publish.
