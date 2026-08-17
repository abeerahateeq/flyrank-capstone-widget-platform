import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

WidgetType = Literal["signup_form", "cta_popover"]


class FieldDef(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=128)
    type: Literal["text", "email", "textarea", "checkbox"] = "text"
    required: bool = False


class WidgetCreate(BaseModel):
    type: WidgetType
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    fields: list[FieldDef] = Field(default_factory=list, max_length=20)
    button_text: str = Field("Submit", max_length=50)
    display_options: dict = Field(default_factory=dict)

    @field_validator("fields")
    @classmethod
    def unique_field_names(cls, v: list[FieldDef]) -> list[FieldDef]:
        names = [f.name for f in v]
        if len(names) != len(set(names)):
            raise ValueError("field names must be unique within a widget")
        return v


class WidgetUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    fields: list[FieldDef] | None = Field(None, max_length=20)
    button_text: str | None = Field(None, max_length=50)
    display_options: dict | None = None
    is_active: bool | None = None


class WidgetOut(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    description: str | None
    fields: list[FieldDef]
    button_text: str
    display_options: dict
    bundle_version: str
    is_active: bool
    embed_snippet: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WidgetConfigOut(BaseModel):
    """What the public /widgets/{id}/config endpoint returns — deliberately
    minimal, no tenant internals, no submission data."""

    id: uuid.UUID
    type: str
    title: str
    description: str | None
    fields: list[FieldDef]
    button_text: str
    display_options: dict
    bundle_version: str
