from app.utils.helpers import ensure_three_recommendations, generate_session_id


def test_generate_session_id_contains_device_prefix():
    session_id = generate_session_id("esp32-a1")
    assert session_id.startswith("esp32-a1-")


def test_ensure_three_recommendations_returns_three_items():
    result = ensure_three_recommendations(["One", "Two"])
    assert len(result) == 3
