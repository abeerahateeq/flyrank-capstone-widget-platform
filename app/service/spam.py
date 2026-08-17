"""Spam detection for public submissions.

Two independent layers, either can flag:
  1. Honeypot: `hp_field` should always arrive empty. Real visitors never
     see it (hidden via CSS in the widget bundle); bots that auto-fill
     every input on a page trip it.
  2. Heuristic: crude link-flooding check on free-text values, catches the
     "here's my spam URL x5" pattern that skips the honeypot entirely.
"""
import re

URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)
MAX_URLS_PER_FIELD = 2


def is_spam(hp_field: str, data: dict[str, str]) -> tuple[bool, str | None]:
    if hp_field:
        return True, "honeypot_filled"

    for field_name, value in data.items():
        if len(URL_PATTERN.findall(value)) > MAX_URLS_PER_FIELD:
            return True, f"link_flood:{field_name}"

    return False, None
