"""Opt in with TEST_DATABASE_URL pointing to an initialized, disposable test DB.

The seed runs in a rolled-back transaction and writes files only to a temp directory.
"""

import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import check_database
from app.seed import seed_demo


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "set TEST_DATABASE_URL to a disposable PostGIS database")
class DatabaseSmokeTests(unittest.TestCase):
    def test_seed_creates_repeatable_demo_with_real_solids(self):
        engine = create_engine(os.environ["TEST_DATABASE_URL"])
        try:
            with engine.connect() as conn, TemporaryDirectory() as demo_dir:
                transaction = conn.begin()
                try:
                    self.assertTrue(check_database(conn)["sfcgal"])
                    with Session(bind=conn) as db, patch.object(settings, "demo_dir", demo_dir):
                        for _ in range(2):
                            result = seed_demo(db)
                            self.assertEqual(result["spatial_units"], 24)
                            self.assertEqual(result["extruded_solids"], 24)
                            missing = db.execute(text("""
                                SELECT count(*) FROM spatial_unit
                                WHERE geom_3d IS NULL OR volume_m3 IS NULL OR volume_m3 <= 0
                            """)).scalar_one()
                            self.assertEqual(missing, 0)
                            volume = db.execute(text("""
                                SELECT volume_m3 FROM spatial_unit WHERE local_code = 'F05-U501'
                            """)).scalar_one()
                            self.assertAlmostEqual(volume, 475.2, places=4)
                finally:
                    if transaction.is_active:
                        transaction.rollback()
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
