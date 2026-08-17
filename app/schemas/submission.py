import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# Hard ceiling on submitted payload size. Anything beyond this many fields
# or characters is rejected with 413 before it ever reaches business logic.
MAX_FIELD_COUNT = 20
MAX_FIELD_VALUE_LEN = 5000


class SubmissionCreate(BaseModel):
    widget_id: uuid.UUID
    data: dict[str, str] = Field(..., max_length=MAX_FIELD_COUNT)
    # Honeypot: a field name real visitors never see or fill (hidden via CSS
    # in the widget bundle). Bots that auto-fill every input trip it.
    hp_field: str = Field("", max_length=200)

    @field_validator("data")
    @classmethod
    def validate_field_values(cls, v: dict[str, str]) -> dict[str, str]:
        for key, value in v.items():
            if len(key) > 64:
                raise ValueError(f"field name too long: {key[:20]}...")
            if len(value) > MAX_FIELD_VALUE_LEN:
                raise ValueError(f"value for '{key}' exceeds {MAX_FIELD_VALUE_LEN} chars")
        return v


class SubmissionOut(BaseModel):
    id: uuid.UUID
    status: str


class SubmissionDetailOut(BaseModel):
    id: uuid.UUID
    widget_id: uuid.UUID
    data: dict
    geo_country: str | None
    geo_city: str | None
    geo_provider: str | None
    spam_flag: bool
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
