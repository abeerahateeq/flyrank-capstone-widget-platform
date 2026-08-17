import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import dashboard, delivery, submissions, widgets
from app.core.config import settings
from app.db.session import Base, engine

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Embeddable Widget & Lead-Capture Platform")

# Public delivery + submission routes are hit from arbitrary customer-site
# origins by design — that's the product. Tighten allow_origins to a known
# allowlist if you're not doing the open "any site can embed this" model.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic validation failures -> clean 400 JSON, never a 500. This is
    the boundary-validation guarantee from the Definition of Done."""
    # exc.errors() can embed a raw Exception object in ctx['error'] when a
    # Pydantic field_validator raises ValueError — jsonable_encoder converts
    # that (and anything else non-serializable) to a plain string so this
    # handler itself can never 500.
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "invalid_payload", "detail": jsonable_encoder(exc.errors())},
    )


app.include_router(widgets.router)
app.include_router(delivery.router)
app.include_router(submissions.router)
app.include_router(dashboard.router)


@app.on_event("startup")
def on_startup():
    # create_all is fine for capstone scope; swap for Alembic migrations
    # before this ever sees production traffic.
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}
