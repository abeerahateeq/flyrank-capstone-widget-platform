from unittest.mock import patch

from app.services.geo import GeoResult, enrich_ip


def test_provider_a_succeeds():
    with patch(
        "app.services.geo._query_provider_a",
        return_value=GeoResult(country="USA", city="Reston", provider="provider_a"),
    ):
        result = enrich_ip("1.1.1.1")
    assert result.provider == "provider_a"
    assert result.country == "USA"


def test_provider_a_fails_provider_b_succeeds():
    with patch("app.services.geo._query_provider_a", side_effect=RuntimeError("timeout")):
        with patch(
            "app.services.geo._query_provider_b",
            return_value=GeoResult(country="Germany", city="Berlin", provider="provider_b"),
        ):
            result = enrich_ip("2.2.2.2")
    assert result.provider == "provider_b"
    assert result.country == "Germany"


def test_both_providers_fail_degrades_without_geo():
    with patch("app.services.geo._query_provider_a", side_effect=RuntimeError("down")):
        with patch("app.services.geo._query_provider_b", side_effect=RuntimeError("down")):
            result = enrich_ip("3.3.3.3")
    assert result == GeoResult(country=None, city=None, provider=None)


def test_no_ip_returns_empty_result_without_calling_providers():
    with patch("app.services.geo._query_provider_a") as mock_a:
        with patch("app.services.geo._query_provider_b") as mock_b:
            result = enrich_ip(None)
    assert result == GeoResult()
    mock_a.assert_not_called()
    mock_b.assert_not_called()


def test_enrichment_failure_never_raises_out_of_submission_endpoint(client, widget):
    """End-to-end: even with both providers down, POST /submissions must
    still succeed (201), proving degrade-never-fail holds through the full
    request path, not just at the service-function level."""
    with patch("app.services.geo._query_provider_a", side_effect=RuntimeError("down")):
        with patch("app.services.geo._query_provider_b", side_effect=RuntimeError("down")):
            resp = client.post(
                "/submissions",
                json={"widget_id": str(widget.id), "data": {"email": "a@b.com"}, "hp_field": ""},
            )
    assert resp.status_code == 201
    assert resp.json()["status"] == "stored"
