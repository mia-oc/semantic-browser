# Versioning

Semantic Browser follows an alpha-first release flow starting at `v1.0`.

## Current baseline

- Release tag baseline: `v1.0`
- Package baseline: `1.0.0`

## Commit-driven increment rule

After `v1.0`, each pushed commit increments the package version using:

- `minor = commits_since_v1_0 // 100`
- `patch = commits_since_v1_0 % 100`
- package version: `1.<minor>.<patch>`

Examples:

- first commit after `v1.0` -> package `1.0.1` (display tag style: `v1.01`)
- tenth commit after `v1.0` -> package `1.0.10` (display tag style: `v1.010`)
- 100th commit after `v1.0` -> package `1.1.0` (display tag style: `v1.1`)

At 1000 commits (`minor == 10`), move to `v2.0`.

## Helper script

Use:

```bash
python tools/next_version.py
```

This prints:

- `commits_since_v1_0`
- canonical package version (`1.x.y`)
- display tag style (`v1...`)

If `v1.0` does not exist yet, the script falls back to counting from repo start and reminds you to create the baseline tag.
