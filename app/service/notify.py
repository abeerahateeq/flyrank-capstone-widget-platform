"""Safe side effects after a submission is stored (confirmation email /
webhook). Contract: this module NEVER raises out to the caller. A failure
here is logged and swallowed — the submission has already been committed
to the database, and that success must stand regardless of what happens
next.
"""
import logging
import uuid

from app.core.config import settings

logger = logging.getLogger("notify")


def send_confirmation(submission_id: uuid.UUID, widget_title: str) -> bool:
    """Returns True if the side effect succeeded, False if it failed —
    callers should log the return value but must NOT let a False value
    change the HTTP response already sent for the submission itself."""
    try:
        if settings.force_email_failure:
            raise RuntimeError("email side effect forced to fail (demo toggle)")

        # Free-tier stand-in for a real ESP/webhook call: log it. Swap this
        # block for an SMTP call via Mailpit, or a requests.post to a
        # webhook URL, without touching the calling code — that's the
        # point of isolating this behind one function.
        logger.info(
            "CONFIRMATION EMAIL (simulated) — submission %s for widget '%s' sent",
            submission_id,
            widget_title,
        )
        return True
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        logger.warning("confirmation side effect failed for %s: %s", submission_id, exc)
        return False
