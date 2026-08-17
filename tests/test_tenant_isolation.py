import uuid


def _create_tenant(db, name="Tenant B"):
    from app.core.auth import hash_api_key
    from app.models.tenant import Tenant

    raw_key = "key-" + uuid.uuid4().hex[:8]
    t = Tenant(name=name, api_key_hash=hash_api_key(raw_key))
    db.add(t)
    db.commit()
    db.refresh(t)
    return t, raw_key


def test_tenant_cannot_read_other_tenants_widget(client, db, tenant, widget):
    _, raw_key_b = _create_tenant(db)
    resp = client.get(f"/api/widgets/{widget.id}", headers={"X-API-Key": raw_key_b})
    assert resp.status_code == 404


def test_tenant_cannot_update_other_tenants_widget(client, db, tenant, widget):
    _, raw_key_b = _create_tenant(db)
    resp = client.patch(
        f"/api/widgets/{widget.id}",
        headers={"X-API-Key": raw_key_b},
        json={"title": "hijacked"},
    )
    assert resp.status_code == 404


def test_tenant_cannot_delete_other_tenants_widget(client, db, tenant, widget):
    _, raw_key_b = _create_tenant(db)
    resp = client.delete(f"/api/widgets/{widget.id}", headers={"X-API-Key": raw_key_b})
    assert resp.status_code == 404


def test_tenant_list_does_not_include_other_tenants_widgets(client, db, tenant, widget):
    _, raw_key_b = _create_tenant(db)
    resp = client.get("/api/widgets", headers={"X-API-Key": raw_key_b})
    assert resp.status_code == 200
    assert resp.json() == []


def test_tenant_cannot_view_other_tenants_dashboard(client, db, tenant, widget):
    _, raw_key_b = _create_tenant(db)
    resp = client.get(
        f"/api/dashboard/widgets/{widget.id}/submissions", headers={"X-API-Key": raw_key_b}
    )
    assert resp.status_code == 404


def test_owner_can_still_access_their_own_widget(client, tenant, widget):
    _, raw_key = tenant
    resp = client.get(f"/api/widgets/{widget.id}", headers={"X-API-Key": raw_key})
    assert resp.status_code == 200
    assert resp.json()["id"] == str(widget.id)


def test_missing_api_key_returns_401(client):
    resp = client.get("/api/widgets")
    assert resp.status_code == 401


def test_wrong_api_key_returns_401(client):
    resp = client.get("/api/widgets", headers={"X-API-Key": "totally-wrong"})
    assert resp.status_code == 401
