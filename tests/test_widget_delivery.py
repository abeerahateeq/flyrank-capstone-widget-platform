def test_create_widget_returns_embed_snippet(client, tenant):
    _, raw_key = tenant
    resp = client.post(
        "/api/widgets",
        headers={"X-API-Key": raw_key},
        json={
            "type": "signup_form",
            "title": "Newsletter",
            "fields": [{"name": "email", "label": "Email", "type": "email", "required": True}],
            "button_text": "Join",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "<script" in body["embed_snippet"]
    assert body["id"] in body["embed_snippet"]


def test_duplicate_field_names_rejected(client, tenant):
    _, raw_key = tenant
    resp = client.post(
        "/api/widgets",
        headers={"X-API-Key": raw_key},
        json={
            "type": "signup_form",
            "title": "Bad Widget",
            "fields": [
                {"name": "email", "label": "Email 1", "type": "email"},
                {"name": "email", "label": "Email 2", "type": "email"},
            ],
        },
    )
    assert resp.status_code == 400


def test_public_config_endpoint_has_cache_header(client, widget):
    resp = client.get(f"/widgets/{widget.id}/config")
    assert resp.status_code == 200
    assert "max-age=60" in resp.headers["cache-control"]
    body = resp.json()
    assert body["title"] == widget.title
    # tenant internals must never leak through the public config endpoint
    assert "tenant_id" not in body


def test_public_config_404_for_unknown_widget(client):
    import uuid

    resp = client.get(f"/widgets/{uuid.uuid4()}/config")
    assert resp.status_code == 404


def test_inactive_widget_not_servable_publicly(client, db, widget):
    widget.is_active = False
    db.add(widget)
    db.commit()
    resp = client.get(f"/widgets/{widget.id}/config")
    assert resp.status_code == 404


def test_widget_bundle_served_with_immutable_cache(client):
    resp = client.get("/widget.js")
    assert resp.status_code == 200
    assert "immutable" in resp.headers["cache-control"]
    assert "application/javascript" in resp.headers["content-type"]
    assert "fetch(apiBase" in resp.text
