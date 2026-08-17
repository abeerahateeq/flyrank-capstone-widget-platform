# BUILDLOG.md

Honest log of where AI (Claude) helped, where it was wrong, and what got
changed. Per the capstone rules: "The AI wrote it" is not an acceptable
answer at demo time, so this log tracks the actual reasoning, not just the
diffs.

## What AI did

- Wrote the initial `DESIGN.md`, all application code (models, schemas,
  repositories, routers, services), the test suite, and this documentation,
  from the Phase 1/2/3 structure in the capstone brief.
- Ran the code against a real Postgres instance and a real running FastAPI
  server (not just read the code) to catch behavior bugs, not just syntax
  errors.

## Where AI was wrong, and what got caught

These were found by actually executing the code end-to-end against live
requests, not by inspection — worth being explicit about since "the AI
wrote it" would be a bad answer to "walk me through this bug":

1. **500 instead of 400 on a validator `ValueError`.** The custom
   `field_validator` in `SubmissionCreate` raises `ValueError` for
   over-length field values. Pydantic v2 embeds that raw exception object
   in `exc.errors()[i]['ctx']['error']`. The FastAPI validation-exception
   handler passed that straight to `JSONResponse`, and `json.dumps` can't
   serialize an `Exception` object — so the handler whose entire job is
   "never let bad input 500" was itself the thing causing the 500. Caught
   by manually curling an oversized payload during Definition-of-Done
   verification, not by writing a test first (the test came after, as a
   regression guard: `test_oversized_field_value_returns_400_not_500`).
   Fix: run `exc.errors()` through `fastapi.encoders.jsonable_encoder`
   before handing it to `JSONResponse`.

2. **Unvalidated client IP could reach a Postgres `INET` column.** The
   original `_client_ip()` just took `X-Forwarded-For` or
   `request.client.host` at face value and passed it straight into an
   `INET` column. Two ways this broke: (a) in tests, Starlette's
   `TestClient` reports its host as the literal string `"testclient"`,
   which isn't a valid IP and raised a `psycopg2.DataError`; (b) more
   importantly, since `X-Forwarded-For` is attacker-controlled input on a
   public endpoint, a malicious or malformed header would have produced
   the same crash in production — a 500 on the one endpoint that most
   needs to never 500. Fix: `_client_ip()` now validates with
   `ipaddress.ip_address()` and falls back to `None` (stored as SQL NULL)
   on anything unparseable, with a warning logged.

3. **Cache header silently dropped on `/widget.js`.** First version
   injected `response: Response` as a FastAPI dependency, set
   `Cache-Control` on it, then returned a *different* `Response` object
   built from `Response(content=..., media_type=...)`. FastAPI uses
   whichever response object you actually return — the headers set on the
   injected one were thrown away. A test written to check for the
   `immutable` cache directive (`test_widget_bundle_served_with_immutable_cache`)
   failed and exposed it immediately. A second attempted fix (mutating
   `.body` on the injected object directly) broke worse — the injected
   response's `status_code` defaults to `None`, which crashed httpx's
   internal logging (`%d format: a real number is required, not NoneType`).
   Final fix: stopped trying to reuse the injected object at all — build
   one `Response(content=..., media_type=..., headers={...})` and return
   only that.

4. **Test-side bug, not an app bug, but worth logging:** several tests
   originally patched `app.services.geo.enrich_ip`, but `submissions.py`
   had done `from app.services.geo import enrich_ip`, which binds a local
   name at import time — patching the source module's attribute doesn't
   touch that already-bound reference, so the mock silently did nothing
   and real (blocked) network calls went out instead. Fixed by changing
   the import in `submissions.py` to `from app.services import geo as
   geo_service` and calling `geo_service.enrich_ip(...)`, so patching
   `app.api.submissions.geo_service.enrich_ip` reliably intercepts it.

## Judgment calls made without being asked, worth knowing about

- **Auth model**: simple bcrypt-hashed API key per tenant (`X-API-Key`
  header), not JWT/OAuth. Chosen for $0-stack simplicity; the design doc
  flags this as a swappable decision, not a hard requirement.
- **Rate limiter**: hand-rolled in-memory sliding window instead of
  `slowapi`, because `slowapi`'s default keying can't cleanly reach into a
  JSON request body for the per-widget limit — reading the body twice
  (once for the limiter, once for the route) adds complexity for no real
  benefit at this scale. Documented as swappable for Redis in
  `app/core/rate_limit.py`'s docstring.
- **Spam submissions are stored, not silently dropped** (`status="rejected",
  spam_flag=true`), so an owner can audit false positives instead of losing
  data with no trace. The brief allows either "silently dropped or
  rejected" — this picks the more debuggable option.
- **Non-goal**: no drag-and-drop widget builder UI. `fields` /
  `display_options` are configured as JSON via the admin API. Recorded
  explicitly in `DESIGN.md § 5` per the brief's requirement for one
  explicit non-goal.

## Stretch goal: targeting rules

Added after every core Definition-of-Done box was already green, per the
brief's rule for § 9.

- Wrote the pure targeting logic (`pathMatches`, `shouldShowOnThisPath`,
  `hasAlreadyBeenSeen`, `markAsSeen`) as standalone JS first, in
  `/tmp/widget_test/targeting.js`, and unit-tested it with a hand-rolled
  Node `assert`-based harness *before* embedding it into the Python-string
  `WIDGET_JS` bundle. This caught nothing wrong in the logic itself, but
  it was worth doing anyway because embedding JS inside a Python
  triple-quoted string means every backslash gets a second layer of
  escaping (`\\]` in the served JS had to become `\\\\]` in the Python
  source) — easy to get subtly wrong and hard to notice by eye.
- After embedding, fetched the *actual* `GET /widget.js` response from the
  running server and ran `node --check` on it (syntax validity), then
  re-ran the same logic tests against the real served file via
  `tests/js/test_targeting.js`, which extracts function bodies by regex
  from whatever file it's given rather than re-declaring them — so it
  tests the real deployed bundle, not a copy that could silently drift.
  This is a stronger check than testing the pre-embedded version alone,
  since a copy-paste or escaping mistake during embedding would still be
  caught.
- Chose `localStorage` for once-per-visitor tracking deliberately — this
  is real product JavaScript running in a *customer's visitor's* browser,
  not a Claude-hosted artifact, so the earlier "never use localStorage in
  artifacts" constraint doesn't apply here; it's the correct tool for
  client-side state that should survive a page reload without a server
  round-trip.
- `hasAlreadyBeenSeen`/`markAsSeen` wrap `localStorage` calls in try/catch
  and fail *open* (show the widget, don't crash) if storage throws — this
  matters because Safari private-browsing and some cookie-blocking
  extensions make `localStorage.setItem` throw rather than silently no-op,
  and a targeting nicety must never be able to break widget delivery on
  the customer's page.

## What a human (you) should still check before treating this as done

- Read every file at least once, not just the tests passing — the tests
  only check what they were written to check.
- The demo script in `README.md` was written to match what was actually
  run and verified above, not aspirationally — but re-run it yourself
  before presenting it live.
- `main.py` uses the deprecated `@app.on_event("startup")` — works fine,
  FastAPI just warns. Left as-is for capstone scope; a `lifespan` context
  manager would be the "no deprecation warnings" version if you want to
  polish further.
