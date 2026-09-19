"""Run from backend: python -m unittest discover -s tests -v."""

import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from app.db import check_database
from app.issuer import assert_parent_ulpin, issue_display_id
from app.main import _startup_schema, health
from app.seed import PARENT_ULPIN
from app.solids import extrude_units


class BaselineTests(unittest.TestCase):
    def test_demo_parent_is_accepted_and_matches_saved_site(self):
        site = Path(__file__).resolve().parents[2] / "data/demo/site.json"
        self.assertEqual(assert_parent_ulpin(PARENT_ULPIN), PARENT_ULPIN)
        self.assertEqual(json.loads(site.read_text())["parent_ulpin"], PARENT_ULPIN)
        self.assertEqual(
            issue_display_id(PARENT_ULPIN, "UNIT", "F05-U501"),
            f"IN-ULPIN3D/{PARENT_ULPIN}/UNIT/F05-U501/v01",
        )

    def test_short_parent_still_rejected(self):
        with self.assertRaisesRegex(ValueError, "14 characters"):
            assert_parent_ulpin("ULPIN14PLACE0")

    def test_startup_does_not_hide_database_failure(self):
        with patch("app.main.ensure_schema", side_effect=RuntimeError("database unavailable")):
            with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                _startup_schema()

    def test_database_requires_schema_and_sfcgal(self):
        for state, message in [
            ({"schema_ready": False, "sfcgal": True}, "schema is missing"),
            ({"schema_ready": True, "sfcgal": False}, "postgis_sfcgal is required"),
        ]:
            with self.subTest(state=state):
                conn = MagicMock()
                conn.execute.return_value.mappings.return_value.one.return_value = state
                with self.assertRaisesRegex(RuntimeError, message):
                    check_database(conn)

    def test_database_rejects_broken_solid_calculation(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.one.return_value = {
            "schema_ready": True, "sfcgal": True,
        }
        for volume in (None, 0, float("nan"), float("inf")):
            with self.subTest(volume=volume):
                conn.execute.return_value.scalar_one.return_value = volume
                with self.assertRaisesRegex(RuntimeError, "expected a 1 m³ cube"):
                    check_database(conn)

    def test_health_cannot_report_ok_when_solid_check_fails(self):
        with patch("app.main.engine"), patch(
            "app.main.check_database", side_effect=RuntimeError("solid check failed")
        ):
            with self.assertRaisesRegex(RuntimeError, "solid check failed"):
                health()

    def test_seed_cannot_silently_skip_solids(self):
        db = MagicMock()
        db.execute.return_value.scalar.return_value = False
        with self.assertRaisesRegex(RuntimeError, "postgis_sfcgal is required"):
            extrude_units(db)


if __name__ == "__main__":
    unittest.main()
