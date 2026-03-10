from semantic_browser.models import ActionRequest, ObservationDelta, PageInfo


def test_page_info_model():
    page = PageInfo(
        url="https://example.com",
        title="Example",
        domain="example.com",
        page_type="generic",
        page_identity="example.com:example",
        ready_state="complete",
        modal_active=False,
        frame_count=1,
    )
    assert page.domain == "example.com"


def test_action_request_defaults():
    req = ActionRequest()
    assert req.options == {}


def test_observation_delta_defaults():
    delta = ObservationDelta()
    assert delta.changed_values == {}
