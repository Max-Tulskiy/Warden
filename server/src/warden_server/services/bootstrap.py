"""One-time startup bootstrap: an initial operator account for a fresh deployment."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from warden_server.models.operator import Operator, OperatorRole
from warden_server.security import hash_password


def ensure_seed_operator(db: Session, *, username: str, password: str) -> None:
    """Create the configured seed operator if no operator exists yet.

    Idempotent and safe to call on every container start: it only acts when
    the `operators` table is completely empty, so it never resets a
    password an administrator has since changed, and never fights with a
    differently-named operator someone created by hand.
    """
    existing = db.execute(select(Operator).limit(1)).scalar_one_or_none()
    if existing is not None:
        return
    db.add(
        Operator(
            username=username,
            password_hash=hash_password(password),
            role=OperatorRole.ADMIN,
        )
    )
