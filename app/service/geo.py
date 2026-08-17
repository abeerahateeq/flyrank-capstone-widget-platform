"""IP -> geolocation enrichment with a provider fallback chain.

Contract: this module NEVER raises. If both providers are down, or the IP
is unroutable (e.g. localhost during dev), it returns a GeoResult with all
fields None. The submission must still be stored — enrichment is a nice-to
-have, not a gate.
"""
import logging
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger("geo")

PROVIDER_TIMEOUT_SECONDS = 3.0


@dataclass
class GeoResult:
    country: str | None = None
    city: str | None = None
    provider: str | None = None  # "provider_a" | "provider_b" | None


def _query_provider_a(ip: str) -> GeoResult | None:
    if settings.force_geo_provider_a_down:
        raise RuntimeError("provider A forced down (demo toggle)")
    url = settings.geo_provider_a_url.format(ip=ip)
    resp = httpx.get(url, timeout=PROVIDER_TIMEOUT_SECONDS)
    resp.raise_for_status()
    body = resp.json()
    if body.get("status") == "fail":
        raise RuntimeError(f"provider A rejected IP: {body.get('message')}")
    return GeoResult(country=body.get("country"), city=body.get("city"), provider="provider_a")


def _query_provider_b(ip: str) -> GeoResult | None:
    if settings.force_geo_provider_b_down:
        raise RuntimeError("provider B forced down (demo toggle)")
    url = settings.geo_provider_b_url.format(ip=ip)
    resp = httpx.get(url, timeout=PROVIDER_TIMEOUT_SECONDS)
    resp.raise_for_status()
    body = resp.json()
    if body.get("error"):
        raise RuntimeError(f"provider B rejected IP: {body.get('reason')}")
    return GeoResult(
        country=body.get("country_name"), city=body.get("city"), provider="provider_b"
    )


def enrich_ip(ip: str | None) -> GeoResult:
    """Try provider A, then provider B, then give up quietly."""
    if not ip:
        return GeoResult()

    for provider_fn, name in ((_query_provider_a, "A"), (_query_provider_b, "B")):
        try:
            result = provider_fn(ip)
            if result:
                return result
        except Exception as exc:  # noqa: BLE001 - intentionally broad: any
            # failure mode (timeout, DNS, 4xx/5xx, bad JSON) falls through
            # to the next provider, never bubbles up to the caller.
            logger.warning("geo provider %s failed for %s: %s", name, ip, exc)
            continue

    logger.warning("all geo providers exhausted for %s, storing without geo", ip)
    return GeoResult()
