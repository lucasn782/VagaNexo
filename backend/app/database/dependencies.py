from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.database.session import SessionLocal


def get_db() -> Iterator[Session]:
    """Provide a request-scoped SQLAlchemy session.

    Services commit their own transactions. Any unhandled error rolls the
    session back before it is closed, so a failed request never leaks a
    partially applied transaction.
    """
    with SessionLocal() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
