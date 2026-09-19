import unittest

from shapely.geometry import Polygon, box

from app.validate import evaluate_units


def unit(code, bounds=(0, 0, 2, 2), z=(0, 3), **extra):
    return {"id": code, "local_code": code, "su_class": "UNIT", "parent_id": "building",
            "srid": 32643, "wkt": box(*bounds).wkt, "zmin": z[0], "zmax": z[1],
            "topology_status": "PENDING", **extra}


def scene(*children):
    return [unit("parcel", (-10, -10, 20, 20), (-5, 20), su_class="PARCEL", parent_id=None),
            unit("building", (-5, -5, 15, 15), (0, 15), su_class="BUILDING", parent_id="parcel"),
            *children]


class ValidationTests(unittest.TestCase):
    def test_overlap_flags_both_without_special_names(self):
        findings, statuses = evaluate_units(scene(unit("a"), unit("b")))
        self.assertEqual(statuses["a"], "INVALID")
        self.assertEqual(statuses["b"], "INVALID")
        self.assertEqual(sum(f["rule_code"] == "UNIT_OVERLAP" for f in findings), 2)

    def test_stacked_and_touching_units_are_valid(self):
        _, statuses = evaluate_units(scene(unit("a"), unit("b", z=(3, 6)),
                                           unit("c", bounds=(2, 0, 4, 2))))
        self.assertTrue(all(s == "VALID" for s in statuses.values()))

    def test_name_does_not_make_a_valid_unit_invalid(self):
        _, statuses = evaluate_units(scene(unit("a-DUP")))
        self.assertEqual(statuses["a-DUP"], "VALID")

    def test_vertical_and_horizontal_containment(self):
        findings, statuses = evaluate_units(scene(unit("high", z=(14, 17)),
            unit("outside", bounds=(16, 0, 18, 2))))
        self.assertEqual(statuses["high"], "INVALID")
        self.assertEqual(statuses["outside"], "INVALID")
        self.assertTrue(any(f["rule_code"] == "PARENT_Z" and not f["passed"] for f in findings))

    def test_missing_parent_and_invalid_polygon(self):
        invalid = Polygon([(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)])
        _, statuses = evaluate_units(scene(unit("orphan", parent_id="absent"),
                                           unit("bad", wkt=invalid.wkt)))
        self.assertEqual(statuses["orphan"], "INVALID")
        self.assertEqual(statuses["bad"], "INVALID")

    def test_repaired_unit_recovers_and_degraded_stays_blocked(self):
        _, statuses = evaluate_units(scene(unit("repaired", topology_status="INVALID"),
            unit("estimated", bounds=(3, 0, 5, 2), topology_status="DEGRADED")))
        self.assertEqual(statuses["repaired"], "VALID")
        self.assertEqual(statuses["estimated"], "DEGRADED")

    def test_floors_are_grouped_by_building(self):
        findings, statuses = evaluate_units(scene(
            unit("building2", su_class="BUILDING", parent_id="parcel", z=(0, 15)),
            unit("f1", su_class="FLOOR"),
            unit("f2", su_class="FLOOR", parent_id="building2")))
        self.assertTrue(all(s == "VALID" for s in statuses.values()))
        self.assertFalse(any(f["rule_code"] in ("FLOOR_GAP", "FLOOR_OVERLAP") for f in findings))

    def test_overlapping_floors_block_descendants(self):
        _, statuses = evaluate_units(scene(unit("f1", su_class="FLOOR", z=(0, 4)),
            unit("f2", su_class="FLOOR", z=(3, 6)), unit("child", parent_id="f1")))
        self.assertEqual(statuses["f1"], "INVALID")
        self.assertEqual(statuses["f2"], "INVALID")
        self.assertEqual(statuses["child"], "INVALID")

    def test_nonfinite_height_is_rejected(self):
        _, statuses = evaluate_units(scene(unit("bad", z=(0, float("inf")))))
        self.assertEqual(statuses["bad"], "INVALID")

    def test_volume_tolerance_not_just_footprint_area(self):
        # 0.004 m² times 3 m = 0.012 m³: above the configured 0.01 m³ tolerance.
        _, statuses = evaluate_units(scene(unit("a", bounds=(0, 0, 1, 1)),
            unit("b", bounds=(0.996, 0, 2, 1))))
        self.assertEqual(statuses["a"], "INVALID")


if __name__ == "__main__":
    unittest.main()
