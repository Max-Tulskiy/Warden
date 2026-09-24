"""Ending an operator's sessions (constitution D-9)."""

from sqlalchemy import update
from sqlalchemy.orm import Session

from warden_server.models.operator import Operator


def end_sessions(db: Session, operator: Operator) -> None:
    """Raise the operator's `token_version`, ending every session issued so far.

    One SQL statement with the increment inside it, not a read-modify-write in
    Python: two requests racing here cannot both write the same value and so
    drop a revocation. The caller commits, and refreshes `operator` if it needs
    the new value.
    """
    db.execute(
        update(Operator)
        .where(Operator.id == operator.id)
        .values(token_version=Operator.token_version + 1)
    )
