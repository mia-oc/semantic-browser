from __future__ import annotations

import json
from pathlib import Path
import sys


REQUIRED_TOP_LEVEL = {"version", "results"}
REQUIRED_RESULT_FIELDS = {"id", "date_utc", "commit", "task_pack", "task_count", "summary", "reports"}


def main() -> int:
    manifest_path = Path("benchmarks/manifest.json")
    if not manifest_path.exists():
        print("benchmarks/manifest.json is missing")
        return 1
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = REQUIRED_TOP_LEVEL.difference(payload.keys())
    if missing:
        print(f"manifest missing keys: {sorted(missing)}")
        return 1
    results = payload.get("results") or []
    if not isinstance(results, list) or not results:
        print("manifest results must contain at least one entry")
        return 1
    for idx, result in enumerate(results):
        missing_fields = REQUIRED_RESULT_FIELDS.difference(result.keys())
        if missing_fields:
            print(f"result[{idx}] missing keys: {sorted(missing_fields)}")
            return 1
    print("benchmark manifest is valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
