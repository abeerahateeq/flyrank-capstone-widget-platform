import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET

from app.db.session import Base


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    widget_id = Column(UUID(as_uuid=True), ForeignKey("widgets.id"), nullable=False)
    # Denormalized on purpose (see DESIGN.md § 2): every tenant-isolation and
    # dashboard query filters on tenant_id directly, no join required.
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)

    data = Column(JSONB, nullable=False)
    ip_address = Column(INET, nullable=True)

    geo_country = Column(String, nullable=True)
    geo_city = Column(String, nullable=True)
    geo_provider = Column(String, nullable=True)  # "provider_a" | "provider_b" | None

    spam_flag = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False, default="stored")  # "stored" | "rejected"

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_submissions_tenant_created", "tenant_id", "created_at"),
        Index("ix_submissions_widget_created", "widget_id", "created_at"),
    )
