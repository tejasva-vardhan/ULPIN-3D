import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import settings
from app.main import fix_overlap, issue_unit, validation_run
from app.seed import seed_demo, degrade_without_plans
from app.validate import run_validation


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "set TEST_DATABASE_URL to a disposable PostGIS database")
class ValidationDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(os.environ["TEST_DATABASE_URL"])
        self.conn = self.engine.connect()
        self.transaction = self.conn.begin()
        self.temp = TemporaryDirectory()
        self.files = patch.object(settings, "demo_dir", self.temp.name)
        self.files.start()
        self.sessions = patch("app.main.SessionLocal", self.session)
        self.sessions.start()
        with self.session() as db:
            seed_demo(db)
            db.commit()

    def session(self):
        return Session(bind=self.conn, join_transaction_mode="create_savepoint")

    def tearDown(self):
        self.sessions.stop()
        self.files.stop()
        self.transaction.rollback()
        self.conn.close()
        self.engine.dispose()
        self.temp.cleanup()

    def test_invalid_issuance_then_repair_preserves_history(self):
        first = self.conn.execute(text("SELECT run_id FROM validation_result LIMIT 1")).scalar_one()
        for code in ("F05-U501", "F05-U501-DUP"):
            with self.assertRaises(HTTPException) as raised:
                issue_unit(code)
            self.assertEqual(raised.exception.status_code, 409)
        result = fix_overlap()
        self.assertEqual(result["flat_501"]["topology_status"], "VALID")
        self.assertEqual(result["validation"]["error_count"], 0)
        self.assertTrue(issue_unit("F05-U501")["issued"])
        self.assertGreater(validation_run(first)["count"], 0)
        status = self.conn.execute(text("SELECT status FROM spatial_unit WHERE local_code='F05-U501-DUP'")).scalar_one()
        self.assertEqual(status, "EXTINGUISHED")
        runs = self.conn.execute(text("SELECT count(DISTINCT run_id) FROM validation_result")).scalar_one()
        self.assertGreaterEqual(runs, 5)

    def test_stale_valid_status_does_not_allow_issuance(self):
        fix_overlap()
        self.conn.execute(text("""
            UPDATE spatial_unit SET zmax = 18, topology_status = 'VALID'
            WHERE local_code = 'F05-U501'
        """))
        with self.assertRaises(HTTPException) as raised:
            issue_unit("F05-U501")
        self.assertEqual(raised.exception.status_code, 409)
        status = self.conn.execute(text("SELECT topology_status FROM spatial_unit WHERE local_code='F05-U501'")).scalar_one()
        self.assertEqual(status, "INVALID")

    def test_repeat_validation_and_degraded_state(self):
        fix_overlap()
        self.conn.execute(text("UPDATE spatial_unit SET topology_status='DEGRADED' WHERE local_code='F05-U501'"))
        with self.session() as db:
            first = run_validation(db)
            second = run_validation(db)
            self.assertNotEqual(first["run_id"], second["run_id"])
            self.assertEqual(first["error_count"], second["error_count"])
            db.commit()
        with self.assertRaises(HTTPException) as raised:
            issue_unit("F05-U501")
        self.assertEqual(raised.exception.status_code, 409)

    def test_no_plans_demo_preserves_evidence_on_repeat(self):
        first = self.conn.execute(text("SELECT run_id FROM validation_result LIMIT 1")).scalar_one()
        for _ in range(2):
            with self.session() as db:
                result = degrade_without_plans(db)
                self.assertEqual(len(result["whole_floor_units"]), 4)
                run_validation(db)
                db.commit()
        self.assertGreater(validation_run(first)["count"], 0)
        with self.assertRaises(HTTPException) as raised:
            issue_unit("F05-WHOLE")
        self.assertEqual(raised.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
