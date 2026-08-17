# EVIDENCE.md

One pasted proof per Definition-of-Done checkbox (brief § 6). All commands
below were run against a local instance (`uvicorn app.main:app`) backed by
the Postgres instance from `docker-compose.yml`, with `python scripts/seed.py`
already run.

---

## WIDGET MANAGEMENT

**Authenticated CRUD; unauthenticated requests rejected**
```
$ curl -s -w "\nSTATUS:%{http_code}\n" http://localhost:8000/api/widgets
{"detail":"missing X-API-Key header"}
STATUS:401

$ curl -s -w "\nSTATUS:%{http_code}\n" -H "X-API-Key: wrong-key" http://localhost:8000/api/widgets
{"detail":"invalid API key"}
STATUS:401
```

**Multi-tenant isolation** — tenant B cannot read, update, delete, or list
tenant A's widget (test file: `tests/test_tenant_isolation.py`):
```
$ python -m pytest tests/test_tenant_isolation.py -v
test_tenant_cannot_read_other_tenants_widget PASSED
test_tenant_cannot_update_other_tenants_widget PASSED
test_tenant_cannot_delete_other_tenants_widget PASSED
test_tenant_list_does_not_include_other_tenants_widgets PASSED
test_tenant_cannot_view_other_tenants_dashboard PASSED
test_owner_can_still_access_their_own_widget PASSED
test_missing_api_key_returns_401 PASSED
test_wrong_api_key_returns_401 PASSED
```
Also verified live with two real seeded tenants — Tenant B's GET/PATCH
against Tenant A's widget both returned `404 {"detail":"widget not found"}`,
and Tenant A retained normal access afterward.

## WIDGET DELIVERY

**Embed snippet generated per widget**
```
$ curl -s -X POST http://localhost:8000/api/widgets -H "X-API-Key: <key>" \
  -H "Content-Type: application/json" \
  -d '{"type":"signup_form","title":"Newsletter","fields":[...]}'
{"id":"...", "embed_snippet":"<script src=\"https://your-domain.com/widget.js?id=...\"></script>", ...}
```

**Public config endpoint, correct cache headers**
```
$ curl -s -D - http://localhost:8000/widgets/<id>/config
HTTP/1.1 200 OK
cache-control: public, max-age=60
{"id":"...","title":"Join our newsletter","fields":[...],...}
```

**Versioned bundle, long/immutable cache**
```
$ curl -s -D - http://localhost:8000/widget.js -o /dev/null | grep -i cache-control
cache-control: public, max-age=31536000, immutable
```

**Renders on a second-origin page** — `customer-site/index.html` served via
`python -m http.server 5500` (origin `http://localhost:5500`), embedding a
widget from `http://localhost:8000`. Confirmed the full chain works
cross-origin: page load → `widget.js` fetch → `/widgets/{id}/config` fetch
(with `access-control-allow-origin: *`) → rendered form → submission POST,
all succeeding with the two servers on different ports/origins.

## PUBLIC SUBMISSION API

**CORS preflight handled correctly**
```
$ curl -s -D - -X OPTIONS http://localhost:8000/submissions \
  -H "Origin: http://localhost:5500" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type"
HTTP/1.1 200 OK
access-control-allow-origin: *
access-control-allow-methods: GET, POST, OPTIONS
access-control-allow-headers: Accept, Accept-Language, Content-Language, Content-Type, X-API-Key
```

**Cross-origin submission succeeds**
```
$ curl -s -D - -X POST http://localhost:8000/submissions \
  -H "Origin: http://localhost:5500" -H "Content-Type: application/json" \
  -d '{"widget_id":"...","data":{"email":"visitor@example.com"},"hp_field":""}'
HTTP/1.1 201 Created
access-control-allow-origin: *
{"id":"...","status":"stored"}
```

**Malformed / oversized payloads → clean 4xx, never 500**
```
$ curl -s -w "\nSTATUS:%{http_code}\n" -X POST http://localhost:8000/submissions \
  -H "Content-Type: application/json" -d '{"widget_id":"not-a-uuid","data":{...}}'
{"error":"invalid_payload","detail":[...]}
STATUS:400

$ curl -s -w "\nSTATUS:%{http_code}\n" -X POST .../submissions -d '{"widget_id":"...","data":{"email":"aaa...(6000 chars)"}}'
{"error":"invalid_payload","detail":[...]}
STATUS:400
```
This surfaced a real bug during manual testing: a Pydantic `field_validator`
`ValueError` embedded a raw exception object in `ctx`, which crashed
`json.dumps` and produced a `500`. Fixed in `app/main.py` by running
`exc.errors()` through `jsonable_encoder` before serializing. Regression
test: `tests/test_submission_validation.py::test_oversized_field_value_returns_400_not_500`.

**Stored correctly, linked to widget + tenant** — confirmed via
`GET /api/dashboard/widgets/{id}/submissions` returning the stored row with
matching `widget_id`.

## ABUSE PROTECTION

**Rate limiting — burst returns 429, legitimate traffic still served**
```
$ for i in $(seq 1 12); do curl -s -o /dev/null -w "%{http_code}\n" -X POST .../submissions -d '{...}'; done
201
201
201
201
201
201
201
201
201
201
429
429
```
Test: `tests/test_abuse_protection.py::test_burst_triggers_429_then_recovers`
and `test_rate_limit_does_not_block_other_ips` (proves a flood from one IP
does not block a different visitor).

**Spam control — honeypot demonstrably blocks a spam submission**
```
$ curl -s -X POST .../submissions -d '{"widget_id":"...","data":{"email":"bot@spam.com"},"hp_field":"i-am-a-bot"}'
{"id":"...","status":"rejected"}

$ psql -c "SELECT status, spam_flag FROM submissions WHERE id='...'"
 status  | spam_flag
----------+-----------
 rejected | t
```
Test: `tests/test_abuse_protection.py::test_honeypot_filled_is_flagged_and_not_stored_as_valid`

## ENRICHMENT & SAFE SIDE EFFECTS

**Provider fallback chain: A down → B answers**
```python
# tests/test_geo_fallback.py::test_provider_a_fails_provider_b_succeeds
with patch("app.services.geo._query_provider_a", side_effect=RuntimeError("timeout")):
    with patch("app.services.geo._query_provider_b", return_value=GeoResult(country="Germany", ...)):
        result = enrich_ip("2.2.2.2")
assert result.provider == "provider_b"   # PASSED
```

**All providers down → submission still succeeds, no geo data**
This was reproduced for real, not just mocked: this dev sandbox has no
outbound network access to `ip-api.com` / `ipapi.co`, so a genuine
submission request hit both real providers, both failed (`403 Forbidden`
from the egress proxy), and the request still returned `201`:
```
WARNING:geo:geo provider A failed for 8.8.8.8: Client error '403 Forbidden' ...
WARNING:geo:geo provider B failed for 8.8.8.8: Client error '403 Forbidden' ...
WARNING:geo:all geo providers exhausted for 8.8.8.8, storing without geo
INFO: 127.0.0.1 - "POST /submissions HTTP/1.1" 201 Created

$ psql -c "SELECT geo_country, geo_city, geo_provider FROM submissions WHERE id='...'"
 geo_country | geo_city | geo_provider
-------------+----------+--------------
             |          |
```
Deterministic mocked version: `tests/test_geo_fallback.py::test_both_providers_fail_degrades_without_geo`
and `test_enrichment_failure_never_raises_out_of_submission_endpoint`.

**Failing email/webhook does not block submission**
```
# .env: FORCE_EMAIL_FAILURE=true
$ curl -s -w "\nSTATUS:%{http_code}\n" -X POST .../submissions -d '{...}'
{"id":"...","status":"stored"}
STATUS:201

# server log:
WARNING:notify:confirmation side effect failed for ...: email side effect forced to fail (demo toggle)
INFO: 127.0.0.1 - "POST /submissions HTTP/1.1" 201 Created
```
Test: `tests/test_safe_side_effects.py::test_email_failure_does_not_block_submission_success`

## TESTS & DOCUMENTATION

**Full automated suite, green**
```
$ python -m pytest tests/ -v
...
32 passed, 6 warnings in 11.10s
```
Covers: CORS preflight, invalid/oversized payload, unknown widget, rate
limiting (own-IP + cross-IP), honeypot + link-flood spam heuristics, geo
fallback (all 3 branches, mocked + real), safe side effects (mocked +
contract test), tenant isolation (6 scenarios), widget CRUD, config caching,
inactive-widget gating, and bundle caching.

**README with architecture diagram, setup, API docs, limitations** — see
`README.md`.

---

## STRETCH GOAL: TARGETING RULES

Implemented only after every box above was green, per the brief's rule for
§ 9. Design: `DESIGN.md` § "Stretch goal: targeting rules".

**Logic tested against the actual live-served bundle, not a copy.** The
test file extracts the real function bodies out of `GET /widget.js`'s
response and evals them — so it fails if the served JS ever drifts from
what's tested, unlike a hand-copied reimplementation would.
```
$ curl -s http://localhost:8000/widget.js -o /tmp/widget.js
$ node tests/js/test_targeting.js /tmp/widget.js
pathMatches: OK
shouldShowOnThisPath: OK
seen/unseen tracking: OK

ALL TARGETING LOGIC TESTS PASSED (against live-served widget.js)
```
Covers: exact path match, wildcard (`/blog/*`) match, non-match, dot-is-
literal-not-regex-wildcard (a real escaping bug class), empty/undefined
target list = show everywhere (backward compatible default), and
localStorage-backed once-per-visitor tracking including that a different
widget ID's "seen" state doesn't leak into another widget's.

**End-to-end via the real API**: created a second widget with
`display_options: {"delay_seconds": 3, "target_paths": ["/pricing",
"/blog/*"], "show_once_per_visitor": true}`, confirmed via
`GET /widgets/{id}/config` that the options round-trip correctly, and
confirmed the existing plain widget's `display_options` were untouched
(backward compatibility). `customer-site/pricing.html` embeds this widget
for a live demo; `customer-site/index.html`'s plain widget is unaffected.

**Fail-open on storage errors verified**: a fake `localStorage` that
throws on every call was passed to `hasAlreadyBeenSeen`/`markAsSeen`
directly (before ever embedding in the bundle) — both returned/completed
without throwing, confirmed with `node tests/js/../` isolated harness
during development (see `BUILDLOG.md`).
