from __future__ import annotations

import subprocess
import sys


BASE_TAG = "v1.0"


def _tag_exists(tag: str) -> bool:
    cmd = ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    return completed.returncode == 0


def _git_count_since(tag: str) -> int:
    if _tag_exists(tag):
        cmd = ["git", "rev-list", "--count", f"{tag}..HEAD"]
    else:
        cmd = ["git", "rev-list", "--count", "HEAD"]
    out = subprocess.check_output(cmd, text=True).strip()
    return int(out)


def _compute_versions(commits_since_base: int) -> tuple[str, str]:
    minor = commits_since_base // 100
    patch = commits_since_base % 100
    if minor >= 10:
        raise ValueError("Commit-driven v1 scheme exceeded 999 commits; move to v2.0")
    canonical = f"1.{minor}.{patch}"
    if commits_since_base == 0:
        display = "v1.0"
    elif minor == 0:
        display = f"v1.0{patch}"
    elif patch == 0:
        display = f"v1.{minor}"
    else:
        display = f"v1.{minor}{patch:02d}"
    return canonical, display


def main() -> int:
    try:
        commits = _git_count_since(BASE_TAG)
        canonical, display = _compute_versions(commits)
    except subprocess.CalledProcessError as exc:
        print(f"Failed to read git history: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if _tag_exists(BASE_TAG):
        print(f"baseline_tag: {BASE_TAG}")
        print(f"commits_since_{BASE_TAG.replace('.', '_')}: {commits}")
    else:
        print(f"baseline_tag: (missing) {BASE_TAG}")
        print("using commits from repository start; create v1.0 tag to lock baseline")
        print(f"commits_since_repo_start: {commits}")
    print(f"package_version: {canonical}")
    print(f"display_tag_style: {display}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
