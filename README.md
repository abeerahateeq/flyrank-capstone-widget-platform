# Embeddable Widget & Lead-Capture Platform

FlyRank Internship · Backend Track · Capstone

Let a customer define a widget, hand them one line of `<script>`, and
safely catch everything the public internet throws back — validated,
spam-filtered, geo-enriched, and dashboarded.

See [`DESIGN.md`](./DESIGN.md) for the full data model, embed flow, and API
contracts, and [`EVIDENCE.md`](./EVIDENCE.md) for proof against every item
in the capstone's Definition of Done.

## Architecture

```
Widget Owner (authenticated, X-API-Key)
 └─► Widget Management API ─► Widget DB (tenant-isolated) ─► embed snippet

Customer Website (any origin)
 └─ <script src="http://api-host/widget.js?id=123">
 └─► GET /widgets/:id/config   (public · cached 60s · CORS: *)
 └─► render widget in the page

Website Visitor
 └─► POST /submissions          (public · CORS: *)
       ├─► widget must exist & be active           (404 otherwise)
       ├─► rate limit (per-IP + per-widget)         (429 on burst)
       ├─► spam check (honeypot + link-flood)        (flagged, still stored)
       ├─► geo enrichment: provider A → provider B → store anyway
       ├─► store submission
       └─► confirmation email (failure never blocks the response above)

Widget Owner (authenticated)
 └─► Dashboard API ◄── submissions + stats + geo breakdown
```

Three actors, three trust levels, three separate route groups
(`app/api/widgets.py`, `app/api/delivery.py` + `app/api/submissions.py`,
`app/api/dashboard.py`) — kept structurally separate so the hardened public
path can't accidentally inherit assumptions from the authenticated one.

## Stack

- **Python 3.12 + FastAPI** — Pydantic models double as the boundary-
  validation layer (bad payload → 4xx automatically).
- **PostgreSQL** (via Docker) — `jsonb` for widget fields/submission data,
  `inet` for IP storage.
- **SQLAlchemy** (sync) for the ORM/repository layer.
- **httpx** for the geo provider calls.
- No Redis, no paid tier, no credit card anywhere in the stack. Rate
  limiting is an in-memory sliding window (see
  `app/core/rate_limit.py` for the note on swapping in Redis later).

## Setup

```bash
git clone <this-repo>
cd flyrank-capstone-widget-platform

cp .env.example .env

docker compose up -d          # starts Postgres on localhost:5432
pip install -r requirements.txt --break-system-packages

python scripts/seed.py        # creates a demo tenant + widget,
                               # prints an API key (shown once) and widget ID

uvicorn app.main:app --reload --port 8000
```

Then serve the customer-site test page from a **different port**, so the
embed is a real cross-origin test:

```bash
cd customer-site
python -m http.server 5500
```

Open `http://localhost:5500` — edit `customer-site/index.html`'s
`<script src="...?id=...">` to the widget ID printed by the seed script if
you re-seed.

## Running tests

```bash
# tests use a separate DB so they never touch dev data
psql -U postgres -c "CREATE DATABASE widget_platform_test OWNER widget_user;"
pytest tests/ -v
```

32 tests, covering CORS preflight, invalid/oversized payloads, rate
limiting (own-IP and cross-IP), honeypot + heuristic spam detection, the
full geo fallback chain (mocked deterministically, per the brief's
guidance), safe side-effect failure handling, six tenant-isolation
scenarios, and widget delivery/caching.

## API summary

| Path | Auth | Notes |
|---|---|---|
| `POST/GET/PATCH/DELETE /api/widgets[/{id}]` | `X-API-Key` | tenant-scoped CRUD |
| `GET /widgets/{id}/config` | public | `Cache-Control: max-age=60` |
| `GET /widget.js` | public | `Cache-Control: immutable, max-age=1y` |
| `POST /submissions` | public, CORS `*` | the hardened path — see above |
| `GET /api/dashboard/widgets/{id}/submissions` | `X-API-Key` | paginated |
| `GET /api/dashboard/widgets/{id}/stats` | `X-API-Key` | counts by day |
| `GET /api/dashboard/stats/geo` | `X-API-Key` | country breakdown |

Full request/response contracts are in `DESIGN.md § 4`.

## Demo flow (matches `EVIDENCE.md`)

1. Create a widget via the authenticated API — get back the `<script>` tag.
2. Open the plain-HTML customer site on a different port — the widget
   renders.
3. Submit it — lands in the dashboard, geo-enriched (or gracefully not, if
   the geo providers are unreachable — see limitations below).
4. Attack it: malformed payload (400), disallowed-looking cross-origin
   request, then a burst (429 after the 10th request in a minute).
5. Flip `FORCE_GEO_PROVIDER_A_DOWN=true` in `.env`, restart, submit again —
   provider B answers instead.
6. Flip `FORCE_EMAIL_FAILURE=true` — submission still returns `201`; the
   failure only shows up in the server log.

## Stretch goal: targeting rules

Beyond the core Definition of Done, widgets support three independent
display controls via `display_options` (see `DESIGN.md` for the full
design):

```json
{"delay_seconds": 3, "target_paths": ["/pricing", "/blog/*"], "show_once_per_visitor": true}
```

`customer-site/pricing.html` demonstrates all three live — the widget
waits 3 seconds, only shows on `/pricing` or `/blog/*`, and won't show
again to the same visitor once seen. `customer-site/index.html`'s plain
widget is unaffected (backward compatible — omitting `display_options`
keys behaves exactly as before this feature existed).

Run the logic's own test suite against whatever `widget.js` your server is
actually serving (not a hand-copied reimplementation — it extracts and
evals the real function bodies from the HTTP response):

```bash
curl -s http://localhost:8000/widget.js -o /tmp/widget.js
node tests/js/test_targeting.js /tmp/widget.js
```

## Limitations, honestly

- **No visual widget builder.** `fields` and `display_options` are
  configured as JSON via the admin API — an explicit non-goal (see
  `DESIGN.md § 5`), to keep this a backend project.
- **Rate limiter is single-process, in-memory.** Fine for local/dev scope;
  swap `app/core/rate_limit.py`'s `_buckets` dict for Redis before running
  more than one worker process.
- **Email side effect is simulated** (logged, not actually sent) — the
  Definition of Done grades that its *failure* doesn't break the main
  path, not that a real email arrives. Swap `app/services/notify.py`'s
  body for a real SMTP/Mailpit call or webhook `POST` without touching any
  calling code.
- **Auth is a single bcrypt-hashed API key per tenant**, not full user
  accounts/JWT. A deliberate simplification for capstone scope — see
  `BUILDLOG.md` for the reasoning.
- **Geo providers can be blocked by network policy** (e.g. corporate
  proxies, this project's own dev sandbox) — when both are unreachable,
  submissions still store successfully with no geo data, which is the
  correct behavior per the Definition of Done, not a bug. `EVIDENCE.md`
  documents this happening for real, not just in a mocked test.
- **`@app.on_event("startup")` is deprecated** in this FastAPI version
  (still works, just warns) — a `lifespan` context manager is the
  warning-free equivalent if you want to clean it up further.
