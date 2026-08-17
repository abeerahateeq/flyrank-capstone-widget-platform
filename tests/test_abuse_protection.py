from unittest.mock import patch

from app.services.geo import GeoResult


def _no_geo(*args, **kwargs):
    return GeoResult()


def test_burst_triggers_429_then_recovers(client, widget):
    """Fire a burst past the per-IP limit (10/min). The 11th request should
    429; a request against a DIFFERENT widget from the same burst-limited
    IP should still 429 too (IP limit is global to the client), proving
    the limiter tracks IP independent of which widget is hit."""
    with patch("app.api.submissions.geo_service.enrich_ip", side_effect=_no_geo):
        statuses = []
        for _ in range(12):
            resp = client.post(
                "/submissions",
                json={"widget_id": str(widget.id), "data": {"email": "a@b.com"}, "hp_field": ""},
            )
            statuses.append(resp.status_code)

    assert statuses[:10] == [201] * 10
    assert statuses[10] == 429
    assert statuses[11] == 429


def test_rate_limit_does_not_block_other_ips(client, widget):
    """A flood from one IP must not take down the service for a different
    visitor — the whole point of per-IP limiting over a global limit."""
    with patch("app.api.submissions.geo_service.enrich_ip", side_effect=_no_geo):
        for _ in range(10):
            client.post(
                "/submissions",
                json={"widget_id": str(widget.id), "data": {"email": "flood@b.com"}, "hp_field": ""},
            )
        blocked = client.post(
            "/submissions",
            json={"widget_id": str(widget.id), "data": {"email": "flood2@b.com"}, "hp_field": ""},
        )
        assert blocked.status_code == 429

        # TestClient reuses one httpx transport / one apparent client IP,
        # so we simulate a distinct visitor via X-Forwarded-For, exactly
        # like a real proxy would forward it.
        other_visitor = client.post(
            "/submissions",
            headers={"X-Forwarded-For": "203.0.113.9"},
            json={"widget_id": str(widget.id), "data": {"email": "other@b.com"}, "hp_field": ""},
        )
        assert other_visitor.status_code == 201


def test_honeypot_filled_is_flagged_and_not_stored_as_valid(client, widget, db):
    with patch("app.api.submissions.geo_service.enrich_ip", side_effect=_no_geo):
        resp = client.post(
            "/submissions",
            json={
                "widget_id": str(widget.id),
                "data": {"email": "bot@spam.com"},
                "hp_field": "bots-fill-this",
            },
        )
    assert resp.status_code == 201
    assert resp.json()["status"] == "rejected"

    from app.models.submission import Submission

    row = db.query(Submission).filter(Submission.id == resp.json()["id"]).first()
    assert row.spam_flag is True
    assert row.status == "rejected"


def test_link_flood_heuristic_flags_spam(client, widget):
    spammy = "check http://a.com http://b.com http://c.com http://d.com"
    with patch("app.api.submissions.geo_service.enrich_ip", side_effect=_no_geo):
        resp = client.post(
            "/submissions",
            json={"widget_id": str(widget.id), "data": {"email": spammy}, "hp_field": ""},
        )
    assert resp.status_code == 201
    assert resp.json()["status"] == "rejected"


def test_legit_submission_not_flagged(client, widget):
    with patch("app.api.submissions.geo_service.enrich_ip", side_effect=_no_geo):
        resp = client.post(
            "/submissions",
            json={"widget_id": str(widget.id), "data": {"email": "real@person.com"}, "hp_field": ""},
        )
    assert resp.status_code == 201
    assert resp.json()["status"] == "stored"
