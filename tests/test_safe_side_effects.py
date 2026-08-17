from unittest.mock import patch

from app.services.geo import GeoResult


def _no_geo(*args, **kwargs):
    return GeoResult()


def test_email_failure_does_not_block_submission_success(client, widget):
    with patch("app.api.submissions.geo_service.enrich_ip", side_effect=_no_geo):
        with patch("app.services.notify.send_confirmation", return_value=False) as mock_notify:
            resp = client.post(
                "/submissions",
                json={"widget_id": str(widget.id), "data": {"email": "a@b.com"}, "hp_field": ""},
            )
    assert resp.status_code == 201
    assert resp.json()["status"] == "stored"
    mock_notify.assert_called_once()


def test_email_exception_is_swallowed_not_raised():
    """The notify module's own contract: it must never raise, only return
    False, regardless of what goes wrong internally."""
    from app.services import notify

    with patch.object(notify.settings, "force_email_failure", True):
        ok = notify.send_confirmation(__import__("uuid").uuid4(), "Some Widget")
    assert ok is False
