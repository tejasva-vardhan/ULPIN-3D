import unittest

from shapely.geometry import Polygon, mapping

from app.geo import CrsError
from app.pipeline.floors import describe_plan_segmentation, propose_floor_segmentation


def feature(code, cls, parent, zmin, zmax, *, level=None, footprint=None):
    properties = {
        "local_code": code, "su_class": cls, "parent_code": parent,
        "zmin": zmin, "zmax": zmax, "geom_origin": "PLAN",
    }
    if level is not None:
        properties["level_index"] = level
    return {"type": "Feature", "properties": properties,
            "geometry": mapping(footprint or Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]))}


class FloorSegmentationTests(unittest.TestCase):
    def test_height_inference_is_explicit_and_review_required(self):
        result = propose_floor_segmentation(2, 11, declared_storeys=None,
                                            assumed_storey_height_m=3)
        self.assertEqual(result["method"], "HEIGHT_BANDS")
        self.assertEqual(result["evidence"], "HEIGHT_INFERRED")
        self.assertEqual(result["boundaries_m"], [2, 5, 8, 11])
        self.assertTrue(result["requires_review"])
        self.assertFalse(result["apartment_boundaries_observed"])

    def test_declared_storeys_control_count_but_remain_proposals(self):
        result = propose_floor_segmentation(0, 10, declared_storeys=4,
                                            assumed_storey_height_m=3)
        self.assertEqual(result["method"], "DECLARED_STOREYS")
        self.assertEqual(result["boundaries_m"], [0, 2.5, 5, 7.5, 10])
        self.assertTrue(result["requires_review"])

    def test_plan_levels_and_apartments_are_reported_as_supplied(self):
        footprint = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        features = [
            feature("B1", "BUILDING", "LOT", 0, 6, footprint=footprint),
            feature("F1", "FLOOR", "B1", 0, 3, level=1, footprint=footprint),
            feature("F2", "FLOOR", "B1", 3, 6, level=2, footprint=footprint),
            feature("U1", "UNIT", "F1", 0, 3, footprint=footprint),
        ]
        result = describe_plan_segmentation(features, "B1", footprint)
        self.assertEqual(result["method"], "PLAN_LEVELS")
        self.assertEqual(result["floor_count"], 2)
        self.assertEqual(result["apartment_boundary_count"], 1)
        self.assertTrue(result["apartment_boundaries_supplied"])
        self.assertFalse(result["apartment_boundaries_observed"])

    def test_overlapping_plan_levels_are_rejected(self):
        footprint = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        features = [
            feature("B1", "BUILDING", "LOT", 0, 6, footprint=footprint),
            feature("F1", "FLOOR", "B1", 0, 3.2, level=1, footprint=footprint),
            feature("F2", "FLOOR", "B1", 3, 6, level=2, footprint=footprint),
        ]
        with self.assertRaisesRegex(CrsError, "overlap vertically"):
            describe_plan_segmentation(features, "B1", footprint)


if __name__ == "__main__":
    unittest.main()
