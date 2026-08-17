# Design Doc — Embeddable Widget & Lead-Capture Platform

## 1. Problem

Let a customer (tenant) create a widget (signup form / CTA / popover), get a
one-line `<script>` embed, install it on any website, and safely collect
submissions from visitors on the open internet — validated, spam-filtered,
geo-enriched, and viewable in a dashboard.

The core engineering problem is not CRUD — it's that the public submission
endpoint receives traffic from browsers we don't control, on origins we don't
control, at a rate we don't control. Everything downstream of that endpoint
must assume hostile input and unreliable dependencies.

## 2. Data model

### `tenants`
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| name | text | |
| api_key_hash | text | hashed, used for admin auth (or swap for JWT — see below) |
| created_at | timestamptz | |

### `widgets`
| column | type | notes |
|---|---|---|
| id | uuid PK | this is the `id` in the embed snippet |
| tenant_id | uuid FK → tenants.id | **indexed**, every query filters on this |
| type | enum(`signup_form`,`cta_popover`) | |
| title | text | |
| description | text nullable | |
| fields | jsonb | `[{name, label, type, required}]` — the form schema |
| button_text | text | |
| display_options | jsonb | color, position, delay, etc. |
| bundle_version | text | bumped on config-affecting change → cache-bust key |
| is_active | boolean | inactive widgets stop rendering |
| created_at / updated_at | timestamptz | |

Index: `(tenant_id)`, unique `(id)` (already PK).

### `submissions`
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| widget_id | uuid FK → widgets.id | **indexed** |
| tenant_id | uuid FK → tenants.id | **denormalized on purpose** — every dashboard/isolation query filters tenant_id directly without a join |
| data | jsonb | the visitor's field answers, post-validation |
| ip_address | inet | raw IP, kept for enrichment + rate-limit auditing |
| geo_country | text nullable | filled by enrichment, null if all providers failed |
| geo_city | text nullable | |
| geo_provider | text nullable | which provider answered — `"provider_a"` / `"provider_b"` / `null` |
| spam_flag | boolean default false | honeypot/heuristic hit — stored, not silently dropped, so owners can audit false positives |
| status | enum(`stored`,`rejected`) | |
| created_at | timestamptz | **indexed**, dashboard queries are time-ranged |

Index: `(tenant_id, created_at)`, `(widget_id, created_at)`.

### `idempotency_keys` (submissions)
| column | type | notes |
|---|---|---|
| key | text PK | client-supplied or hash of (widget_id + IP + payload + minute-bucket) |
| submission_id | uuid | |
| created_at | timestamptz | expire/GC after 24h |

**Tenant isolation rule:** every repository method that touches `widgets` or
`submissions` takes `tenant_id` as a mandatory first argument and includes it
in the `WHERE` clause — never optional, never inferred after the fact. This
is enforced at the repository layer, not the API layer, so it can't be
bypassed by a new route.

## 3. The embed flow

```
1. Owner (authenticated) creates widget → gets back { id, embed_snippet }
2. Customer pastes: <script src="https://api/widget.js?id={id}"></script>
3. Browser loads widget.js (public, versioned, cache: immutable)
4. widget.js reads its own ?id=, fetches GET /widgets/{id}/config
   (public, cached short-TTL, CORS: *)
5. widget.js renders a form into the page from that config
6. Visitor submits → POST /submissions (public, CORS: *, this is the
   hardened path: validate → rate-limit/spam → enrich → store → side-effect)
7. Owner (authenticated) later views it via GET /dashboard/...
```

Three actors, three trust levels, three separate route groups — see § 4.

## 4. API contracts

### A. Owner / admin API — authenticated, tenant-scoped

```
POST   /api/widgets                  create widget
GET    /api/widgets                  list own widgets
GET    /api/widgets/{id}             get one (404 if not owned)
PATCH  /api/widgets/{id}             update
DELETE /api/widgets/{id}             delete

GET    /api/dashboard/widgets/{id}/submissions   paginated, filterable
GET    /api/dashboard/widgets/{id}/stats         counts over time
GET    /api/dashboard/stats/geo                  geo breakdown across widgets
```
Auth: `Authorization: Bearer <api_key>` → resolved to `tenant_id`. Every
handler above receives `tenant_id` from the auth dependency, never from the
request body/path, and passes it into the repository layer.

### B. Widget delivery — public, cache-optimized

```
GET /widget.js                 versioned bundle, Cache-Control: public, max-age=31536000, immutable
GET /widgets/{id}/config        Cache-Control: public, max-age=60
                                 CORS: Access-Control-Allow-Origin: *
```
Config response is intentionally minimal: fields, labels, button text,
display options. No tenant internals, no submission counts.

### C. Public submission — hardened path

```
OPTIONS /submissions            CORS preflight, must respond before any auth/DB touch
POST    /submissions            body: { widget_id, data: {...}, honeypot: "" }
```
Response contract:
- `201` → `{ id, status: "stored" }` (even if enrichment/email failed)
- `400` → `{ error, fields: {...} }` malformed
- `413` → payload too large
- `429` → `{ error: "rate_limited", retry_after }`
- **never `500`** for bad client input — 500 is reserved for our own bugs

## 5. Non-goal (explicit)

**Not building:** a visual drag-and-drop widget builder or a WYSIWYG theme
editor. `fields` and `display_options` are configured via JSON in the admin
API. This keeps the project a backend capstone — the "form builder UI" is a
different (frontend) project and would dilute time away from CORS,
rate-limiting, and fallback-chain work, which is the actual point.

## Stretch goal: targeting rules

Implemented after the core (§ 6) shipped, per the brief's "only after every
box is green" rule. Three independent targeting controls, all read from
`display_options` (no schema migration needed — it's already JSONB):

```json
{
  "display_options": {
    "delay_seconds": 5,
    "target_paths": ["/pricing", "/blog/*"],
    "show_once_per_visitor": true
  }
}
```

- **`delay_seconds`** — widget waits N seconds after page load before
  rendering. Pure `setTimeout`, no state needed.
- **`target_paths`** — glob-style path patterns (`*` wildcard only, kept
  simple). Checked against `window.location.pathname`. Omit the key or
  leave it empty to show on every page (default, backward-compatible with
  existing widgets that don't set it).
- **`show_once_per_visitor`** — uses `localStorage`, keyed per widget ID,
  so a visitor who already saw (or dismissed) the widget doesn't see it
  again on a later page load. This is real product code running in the
  *customer's* browser, not a Claude artifact, so `localStorage` is the
  correct and only sensible choice here — no server round-trip needed to
  remember "this visitor already saw this."

All three are independent and additive: a widget can use any combination,
or none (fully backward compatible with widgets created before this
feature — `display_options: {}` behaves exactly as it did before).

## 6. Why FastAPI + Postgres

- Pydantic models double as the boundary-validation layer (bad payload → 4xx
  automatically, satisfies Definition-of-Done § "validation at the boundary").
- `asyncio` fits the enrichment fallback chain naturally (`asyncio.wait_for`
  per provider, sequential fallback on timeout/error).
- Postgres `jsonb` fits `fields`/`data` without a rigid schema migration per
  widget type; `inet` type fits `ip_address` natively.
