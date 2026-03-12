from __future__ import annotations

import json

from semantic_browser.telemetry.debug_dump import export_json_bundle


def test_export_trace_redacts_sensitive_values(tmp_path):
    out = tmp_path / "trace.json"
    export_json_bundle(
        str(out),
        {
            "events": [
                {"kind": "action_request", "payload": {"action_id": "a1", "value": "super-secret"}},
                {"kind": "auth", "payload": {"token": "abc123"}},
            ]
        },
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["events"][0]["payload"]["value"] == "[REDACTED]"
    assert payload["events"][1]["payload"]["token"] == "[REDACTED]"
