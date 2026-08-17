import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Index

from app.db.session import Base


class Widget(Base):
    __tablename__ = "widgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)

    type = Column(String, nullable=False)  # "signup_form" | "cta_popover"
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    fields = Column(JSONB, nullable=False, default=list)
    button_text = Column(String, nullable=False, default="Submit")
    display_options = Column(JSONB, nullable=False, default=dict)

    # Bumped whenever config changes, used to cache-bust the public config
    # endpoint and (optionally) the bundle URL.
    bundle_version = Column(String, nullable=False, default="1")
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (Index("ix_widgets_tenant_id", "tenant_id"),)
