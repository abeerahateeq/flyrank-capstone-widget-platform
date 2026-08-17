import ipaddress
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.rate_limit import enforce as enforce_rate_limit
from app.db.session import get_db
from app.repositories import submission_repo, widget_repo
from app.schemas.submission import SubmissionCreate, SubmissionOut
from app.services import notify
from app.services import geo as geo_service
from app.services.spam import is_spam

router = APIRouter(tags=["submissions"])
logger = logging.getLogger("submissions")


def _client_ip(request: Request) -> str | None:
    """Returns a validated IP string, or None if nothing valid is
    available. This MUST be defensive: X-Forwarded-For is attacker-
    controlled input on the public submission path — a malformed or
    spoofed value must never reach the database (the ip_address column is
    Postgres INET, which raises on invalid input) or crash the request.
    """
    # Trust X-Forwarded-For only if you sit behind a known proxy/LB in
    # production; for local dev, request.client.host is the real source.
    forwarded = request.headers.get("x-forwarded-for")
    candidate = forwarded.split(",")[0].strip() if forwarded else None
    if not candidate and request.client:
        candidate = request.client.host

    if not candidate:
        return None
    try:
        ipaddress.ip_address(candidate)
        return candidate
    except ValueError:
        logger.warning("unparseable client IP %r, storing submission without one", candidate)
        return None


@router.post("/submissions", response_model=SubmissionOut, status_code=201)
def create_submission(payload: SubmissionCreate, request: Request, db: Session = Depends(get_db)):
    """The hardened path. Order matters:
    1. widget must exist and be active (404 otherwise — don't leak which
       widget IDs exist to an attacker probing blind, but this is also just
       correctness: no widget, nothing to submit to)
    2. rate limit — cheapest check, reject floods before touching the DB
    3. spam check — cheap, in-process
    4. geo enrichment — external calls, fallback chain, never blocks storage
    5. store
    6. side effect (email) — fire-and-forget-safe, failure never undoes step 5
    """
    widget = widget_repo.get_public(db, payload.widget_id)
    if not widget:
        raise HTTPException(status_code=404, detail="widget not found")

    ip = _client_ip(request)
    # Rate limiting still needs a key even with no parseable IP - fall back
    # to a shared bucket rather than skipping the limit entirely, since an
    # attacker could otherwise send garbage IPs to dodge it.
    enforce_rate_limit(ip=ip or "unknown", widget_id=str(payload.widget_id))

    spam, spam_reason = is_spam(payload.hp_field, payload.data)

    geo = geo_service.enrich_ip(ip)

    submission = submission_repo.create(
        db,
        widget_id=widget.id,
        tenant_id=widget.tenant_id,
        data=payload.data,
        ip_address=ip,
        geo_country=geo.country,
        geo_city=geo.city,
        geo_provider=geo.provider,
        spam_flag=spam,
        # Spam submissions are still stored (auditable, not silently
        # vanished from the owner's view) but flagged so dashboards and
        # exports can exclude them. See DESIGN.md sect 2.
        status="rejected" if spam else "stored",
    )

    if spam:
        logger.info("submission %s flagged as spam (%s)", submission.id, spam_reason)
        # Do not fire the confirmation side effect for spam.
        return SubmissionOut(id=submission.id, status=submission.status)

    ok = notify.send_confirmation(submission.id, widget.title)
    if not ok:
        # Logged inside notify.send_confirmation already. The submission
        # response below is unaffected by this failure - that's the whole
        # point of "safe side effects" in the Definition of Done.
        pass

    return SubmissionOut(id=submission.id, status=submission.status)
