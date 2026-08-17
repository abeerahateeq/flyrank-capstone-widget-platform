"""Seed a demo tenant + widget for local dev / demo.

Usage:
    python scripts/seed.py

Prints the plaintext API key ONCE — it is never recoverable after this
(only the bcrypt hash is stored), matching how a real system would issue
credentials.
"""
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.auth import hash_api_key
from app.db.session import Base, SessionLocal, engine
from app.models.tenant import Tenant
from app.models.widget import Widget


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    raw_key = secrets.token_urlsafe(24)
    tenant = Tenant(name="Demo Co", api_key_hash=hash_api_key(raw_key))
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    widget = Widget(
        tenant_id=tenant.id,
        type="signup_form",
        title="Join our newsletter",
        description="Get product updates, no spam.",
        fields=[
            {"name": "email", "label": "Your email", "type": "email", "required": True},
            {"name": "name", "label": "Your name", "type": "text", "required": False},
        ],
        button_text="Subscribe",
        display_options={"position": "bottom-right", "theme": "light"},
    )
    db.add(widget)
    db.commit()
    db.refresh(widget)

    # Second widget: same tenant, demonstrates the targeting-rules stretch
    # goal (delay, path matching, once-per-visitor). See DESIGN.md's
    # "Stretch goal: targeting rules" section.
    targeted_widget = Widget(
        tenant_id=tenant.id,
        type="cta_popover",
        title="Special offer, just for you",
        description="Appears once, after a short delay, only on /pricing.",
        fields=[{"name": "email", "label": "Your email", "type": "email", "required": True}],
        button_text="Claim it",
        display_options={
            "delay_seconds": 3,
            "target_paths": ["/pricing", "/blog/*"],
            "show_once_per_visitor": True,
        },
    )
    db.add(targeted_widget)
    db.commit()
    db.refresh(targeted_widget)

    print("=" * 60)
    print(f"Tenant:    {tenant.name} ({tenant.id})")
    print(f"API key:   {raw_key}   <-- save this, shown once")
    print(f"Widget ID (plain):     {widget.id}")
    print(f"Widget ID (targeted):  {targeted_widget.id}")
    print()
    print("Embed snippet for customer-site/index.html:")
    print(f'  <script src="http://localhost:8000/widget.js?id={widget.id}"></script>')
    print()
    print("Embed snippet for customer-site/pricing.html (targeting demo):")
    print(f'  <script src="http://localhost:8000/widget.js?id={targeted_widget.id}"></script>')
    print("=" * 60)

    db.close()


if __name__ == "__main__":
    main()
