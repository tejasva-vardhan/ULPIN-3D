import json
from pathlib import Path
import unittest

from shapely.geometry import shape

from app.ingest import normalize_features
from app.properties import property_features


EXAMPLE = Path(__file__).resolve().parents[2] / "data/examples/dsce_mechanical_block_05.geojson"
OSM_SOURCE = Path(__file__).resolve().parents[2] / "data/examples/dsce_block_osm_way_347171800.geojson"
TWO_BUILDING_EXAMPLE = Path(__file__).resolve().parents[2] / "data/examples/dsce_two_building_demo.geojson"
OSM_SOURCE_EEE = Path(__file__).resolve().parents[2] / "data/examples/dsce_block_osm_way_347591729.geojson"


class DsceExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        cls.source = json.loads(OSM_SOURCE.read_text(encoding="utf-8"))
        cls.normalized = normalize_features(cls.raw, 4326)
        cls.rows = property_features(cls.normalized, None)

    def test_has_one_analysis_envelope_building_and_three_floors(self):
        self.assertEqual(len(self.rows), 5)
        self.assertEqual([row["cls"] for row in self.rows],
                         ["PARCEL", "BUILDING", "FLOOR", "FLOOR", "FLOOR"])
        self.assertEqual([row["level"] for row in self.rows[2:]], [0, 1, 2])

    def test_preserves_osm_building_footprint(self):
        source_geometry = shape(self.source["features"][0]["geometry"])
        building_geometry = shape(self.raw["features"][1]["geometry"])
        self.assertTrue(building_geometry.equals_exact(source_geometry, tolerance=0))
        self.assertEqual(self.raw["features"][1]["properties"]["footprint_source"],
                         "OpenStreetMap way/347171800")

    def test_hierarchy_is_complete_and_floor_bands_do_not_overlap(self):
        by_code = {row["code"]: row for row in self.rows}
        building = by_code["DSCE-MECH-05"]
        self.assertEqual(building["parent_code"], "DSCE-MECH-05-SITE")
        floors = sorted((row for row in self.rows if row["cls"] == "FLOOR"),
                        key=lambda row: row["level"])
        self.assertTrue(all(row["parent_code"] == building["code"] for row in floors))
        self.assertEqual([(row["zmin"], row["zmax"]) for row in floors],
                         [(0.0, 3.0), (3.0, 6.0), (6.0, 9.0)])
        self.assertTrue(all(left["zmax"] <= right["zmin"]
                            for left, right in zip(floors, floors[1:])))

    def test_assumed_geometry_is_blocked_for_human_review(self):
        self.assertTrue(all(feature["properties"]["requires_review"]
                            for feature in self.raw["features"]))
        self.assertTrue(all(row["topology_status"] == "DEGRADED" for row in self.rows))
        self.assertIn("not a legal cadastral boundary", self.raw["description"])
        self.assertIn("measurement pending", self.raw["source"]["vertical_basis"])

    def test_two_building_case_preserves_both_osm_footprints(self):
        combined = json.loads(TWO_BUILDING_EXAMPLE.read_text(encoding="utf-8"))
        sources = {
            "DSCE-MECH-05": json.loads(OSM_SOURCE.read_text(encoding="utf-8")),
            "DSCE-EEE-07": json.loads(OSM_SOURCE_EEE.read_text(encoding="utf-8")),
        }
        by_id = {feature["id"]: feature for feature in combined["features"]}
        for code, source in sources.items():
            with self.subTest(code=code):
                self.assertTrue(shape(by_id[code]["geometry"]).equals_exact(
                    shape(source["features"][0]["geometry"]), tolerance=0))
        self.assertEqual(by_id["DSCE-EEE-07"]["properties"]["label"],
                         "Building No. 07 — Department of Electrical & Electronics Engineering")

    def test_two_building_case_has_valid_hierarchies_and_review_blocks(self):
        combined = json.loads(TWO_BUILDING_EXAMPLE.read_text(encoding="utf-8"))
        rows = property_features(normalize_features(combined, 4326), None)
        self.assertEqual(len(rows), 9)
        self.assertEqual(sum(row["cls"] == "BUILDING" for row in rows), 2)
        self.assertEqual(sum(row["cls"] == "FLOOR" for row in rows), 6)
        self.assertTrue(all(row["topology_status"] == "DEGRADED" for row in rows))
        floors = [row for row in rows if row["cls"] == "FLOOR"]
        for building in ("DSCE-MECH-05", "DSCE-EEE-07"):
            levels = sorted((row for row in floors if row["parent_code"] == building),
                            key=lambda row: row["level"])
            self.assertEqual([(row["zmin"], row["zmax"]) for row in levels],
                             [(0.0, 3.0), (3.0, 6.0), (6.0, 9.0)])


if __name__ == "__main__":
    unittest.main()
