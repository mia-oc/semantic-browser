from semantic_browser.extractor.ids import assign_node_ids, fingerprint_for


def test_fingerprint_stable_for_same_node():
    node = {"role": "button", "tag": "button", "name": "Submit", "type": "", "href": ""}
    assert fingerprint_for(node) == fingerprint_for(node)


def test_assign_node_ids_reuses_previous_map():
    node = {"role": "button", "tag": "button", "name": "Submit", "type": "", "href": ""}
    fp = fingerprint_for(node)
    key = f"{fp}#0"
    ids = assign_node_ids([node], previous={key: "elm-existing"})
    assert ids[key] == "elm-existing"


def test_fingerprint_ignores_rect_y():
    """Nodes with different rect.y but same structural identity produce the same fingerprint."""
    base = {"role": "button", "tag": "button", "name": "Click", "type": "", "href": "",
            "id": "btn1", "css_selector": "#btn1"}
    node_a = {**base, "rect": {"y": 100}}
    node_b = {**base, "rect": {"y": 500}}
    assert fingerprint_for(node_a) == fingerprint_for(node_b)


def test_fingerprint_uses_dom_id():
    """Nodes with different DOM ids produce different fingerprints."""
    base = {"role": "button", "tag": "button", "name": "Click", "type": "", "href": "",
            "css_selector": "button.btn"}
    node_a = {**base, "id": "btn-a"}
    node_b = {**base, "id": "btn-b"}
    assert fingerprint_for(node_a) != fingerprint_for(node_b)


def test_fingerprint_uses_css_selector():
    """Nodes with different CSS selectors produce different fingerprints."""
    base = {"role": "button", "tag": "button", "name": "Click", "type": "", "href": "", "id": ""}
    node_a = {**base, "css_selector": "#parent > button.a"}
    node_b = {**base, "css_selector": "#parent > button.b"}
    assert fingerprint_for(node_a) != fingerprint_for(node_b)
