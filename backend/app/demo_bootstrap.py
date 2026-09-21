"""Initialize the isolated demo database once without resetting later changes."""

from sqlalchemy import text

from app.db import SessionLocal, ensure_schema
from app.seed import seed_demo


def main() -> None:
    ensure_schema()
    with SessionLocal.begin() as db:
        existing = db.execute(text("""
            SELECT
              (SELECT count(*) FROM site) AS sites,
              (SELECT count(*) FROM spatial_unit) AS units,
              (SELECT count(*) FROM source_dataset) AS datasets
        """)).mappings().one()
        if any(existing.values()):
            print(f"Demo database already contains data; preserving it: {dict(existing)}", flush=True)
            return
        result = seed_demo(db)
        print(f"Seeded {result['spatial_units']} demo spatial units and "
              f"{result['extruded_solids']} solids", flush=True)


if __name__ == "__main__":
    main()
