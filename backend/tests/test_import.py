import copy
import json
from pathlib import Path
import unittest

from app.geo import CrsError, require_epsg
from app.ingest import normalize_features
from app.properties import property_features

EXAMPLE = Path(__file__).resolve().parents[2] / 'data/examples/property_import.geojson'


def example():
    return json.loads(EXAMPLE.read_text())


class ImportTests(unittest.TestCase):
    def test_preserves_individual_features_ids_and_properties(self):
        raw = example()
        features = normalize_features(raw, 32643)
        self.assertEqual(len(features), 6)
        self.assertEqual(features[3]['id'], 'U1')
        self.assertEqual(features[3]['properties'], raw['features'][3]['properties'])
        self.assertEqual(len(property_features(features, None)), 6)

    def test_rejects_missing_and_invalid_crs(self):
        for value in (None, 'bad', 999999999, True, 4326.5):
            with self.subTest(value=value), self.assertRaises(CrsError):
                require_epsg(value)

    def test_rejects_empty_or_null_geometry_without_dropping_features(self):
        for raw in ({'type':'FeatureCollection','features':[]},
                    {'type':'Feature','geometry':None,'properties':{}}):
            with self.subTest(raw=raw), self.assertRaises(CrsError):
                normalize_features(raw, 32643)

    def test_rejects_missing_heights_origin_and_duplicate_codes(self):
        for key in ('zmin', 'zmax', 'geom_origin'):
            raw = example()
            del raw['features'][3]['properties'][key]
            with self.subTest(key=key), self.assertRaises(CrsError):
                property_features(normalize_features(raw, 32643), None)
        raw = example()
        raw['features'].append(copy.deepcopy(raw['features'][3]))
        with self.assertRaisesRegex(CrsError, 'duplicate local_code'):
            property_features(normalize_features(raw, 32643), None)

    def test_rejects_multipolygon_for_property_construction(self):
        raw = example()
        geometry = raw['features'][3]['geometry']
        geometry['type'] = 'MultiPolygon'
        geometry['coordinates'] = [geometry['coordinates']]
        with self.assertRaisesRegex(CrsError, '2D Polygon'):
            property_features(normalize_features(raw, 32643), None)

    def test_rejects_nonfinite_height(self):
        raw = example()
        raw['features'][3]['properties']['zmax'] = float('inf')
        with self.assertRaises(CrsError):
            property_features(normalize_features(raw, 32643), None)


if __name__ == '__main__':
    unittest.main()
