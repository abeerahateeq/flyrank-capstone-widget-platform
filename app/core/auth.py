from fastapi import Depends, Header, HTTPException, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.tenant import Tenant

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_api_key(raw_key: str) -> str:
    return pwd_context.hash(raw_key)


def verify_api_key(raw_key: str, hashed: str) -> bool:
    return pwd_context.verify(raw_key, hashed)


def get_current_tenant(
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Tenant:
    """Resolves the caller's tenant from X-API-Key. This is the ONLY place
    tenant identity enters the system for authenticated routes — handlers
    must use tenant.id from here, never a tenant_id from the request body
    or path, or tenant isolation can be bypassed by a malicious client."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="missing X-API-Key header")

    # bcrypt can't look up by hash, so in a real system you'd index by a
    # key prefix. For capstone scope, linear scan over tenants is fine.
    tenants = db.query(Tenant).all()
    for tenant in tenants:
        if verify_api_key(x_api_key, tenant.api_key_hash):
            return tenant

    raise HTTPException(status_code=401, detail="invalid API key")
