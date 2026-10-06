#!/usr/bin/env bash
# Build, check and upload the current version to PyPI.
#   scripts/publish.sh            # dry run: build + twine check only
#   scripts/publish.sh --upload   # really upload (needs .env with TWINE_USERNAME/TWINE_PASSWORD)
# Credentials come from .env (gitignored) or the environment; they are never printed.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-.venv/bin/python}"
version="$("$PY" - <<'EOF'
import re, pathlib
print(re.search(r'^version = "([^"]+)"', pathlib.Path("pyproject.toml").read_text(), re.M).group(1))
EOF
)"
pkg_version="$("$PY" -c 'import semantic_browser; print(semantic_browser.__version__)')"
if [ "$version" != "$pkg_version" ]; then
  echo "version mismatch: pyproject=$version package=$pkg_version" >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "working tree is not clean; commit first" >&2
  exit 1
fi

rm -rf dist
"$PY" -m build --outdir dist . >/dev/null
"$PY" -m twine check dist/*
echo "built semantic-browser $version"

if [ "${1:-}" != "--upload" ]; then
  echo "dry run only (pass --upload to publish)"
  exit 0
fi

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi
: "${TWINE_USERNAME:?missing TWINE_USERNAME (see .env.example)}"
: "${TWINE_PASSWORD:?missing TWINE_PASSWORD (see .env.example)}"
"$PY" -m twine upload --non-interactive dist/*
echo "uploaded semantic-browser $version"
