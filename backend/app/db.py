from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def ensure_schema() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE spatial_unit
                  ADD COLUMN IF NOT EXISTS derived_from uuid REFERENCES spatial_unit(id)
                """
            )
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
