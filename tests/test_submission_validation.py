def test_cors_preflight_allows_cross_origin_post(client, widget):
    resp = client.options(
        "/submissions",
        headers={
            "Origin": "http://localhost:5500",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "*"
    assert "POST" in resp.headers["access-control-allow-methods"]


def test_invalid_payload_returns_400_not_500(client, widget):
    resp = client.post(
        "/submissions",
        json={"widget_id": "not-a-uuid", "data": {"email": "x@example.com"}, "hp_field": ""},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_payload"


def test_wrong_field_type_returns_400(client, widget):
    resp = client.post(
        "/submissions",
        json={"widget_id": str(widget.id), "data": {"email": 12345}, "hp_field": ""},
    )
    assert resp.status_code == 400


def test_oversized_field_value_returns_400_not_500(client, widget):
    """Regression test: a Pydantic field_validator ValueError used to leak
    a non-JSON-serializable exception into the response body, crashing the
    encoder and producing a 500. See app/main.py's exception_handler."""
    resp = client.post(
        "/submissions",
        json={"widget_id": str(widget.id), "data": {"email": "a" * 6000}, "hp_field": ""},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_payload"


def test_too_many_fields_returns_400(client, widget):
    huge_data = {f"field_{i}": "x" for i in range(25)}
    resp = client.post(
        "/submissions",
        json={"widget_id": str(widget.id), "data": huge_data, "hp_field": ""},
    )
    assert resp.status_code == 400


def test_unknown_widget_returns_404_not_500(client):
    import uuid

    resp = client.post(
        "/submissions",
        json={"widget_id": str(uuid.uuid4()), "data": {"email": "x@example.com"}, "hp_field": ""},
    )
    assert resp.status_code == 404
