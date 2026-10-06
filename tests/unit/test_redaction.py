from semantic_browser.config import RedactionConfig
from semantic_browser.extractor.redaction import redact_nodes


def test_redact_password_and_tokens():
    nodes = [
        {"type": "password", "name": "Password", "text": "hunter2"},
        {"type": "text", "name": "API token", "text": "abc"},
    ]
    out = redact_nodes(nodes, RedactionConfig(enabled=True, expose_secrets=False))
    assert out[0]["name"] == "Password"          # the label stays usable ("Confirm password" must not become "Password [REDACTED]")
    assert out[0]["text"] == "" and "hunter2" not in str(out[0])   # the secret itself never survives
    assert out[1]["text"] == "[REDACTED]"
    assert redact_nodes([{"type": "password", "name": "", "text": "x"}], RedactionConfig(enabled=True, expose_secrets=False))[0]["name"] == "Password"
    assert redact_nodes([{"type": "password", "name": "Confirm password"}], RedactionConfig(enabled=True, expose_secrets=False))[0]["name"] == "Confirm password"
