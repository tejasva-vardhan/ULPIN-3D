from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from shapely.geometry import box, LineString, mapping

from app.geo import CrsError
from app.pipeline.assets import inspect_asset
from app.pipeline.measure import measure_cloud, measure_rasters
from app.properties import property_features
from elevation_fixtures import cloud_file, raster_file


class ElevationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.parcel = box(500000, 2050000, 500030, 2050020)

    def tearDown(self):
        self.temp.cleanup()

    def test_cloud_reads_classified_roof_without_ground_beneath_building(self):
        path = cloud_file(self.root/'cloud.las')
        result = measure_cloud(path, 32643, 430, self.parcel)
        self.assertAlmostEqual(result['height_m'], 9, places=3)
        self.assertEqual(result['method'], 'classified-building-points')
        self.assertTrue(self.parcel.covers(result['footprint']))

    def test_laz_and_geographic_reprojection(self):
        path = cloud_file(self.root/'cloud.laz', epsg=4326)
        self.assertEqual(inspect_asset(path, 'las')['source_epsg'], 4326)
        result = measure_cloud(path, 4326, 430, self.parcel)
        self.assertAlmostEqual(result['height_m'], 9, places=3)

    def test_unclassified_cloud_declares_ground_assumption(self):
        path = cloud_file(self.root/'cloud.las', classified=False)
        result = measure_cloud(path, 32643, 430, self.parcel)
        self.assertEqual(result['confidence'], 0.35)
        self.assertTrue(any('Ground estimated' in item for item in result['assumptions']))

    def test_missing_and_conflicting_crs(self):
        path = cloud_file(self.root/'missing.las', header_crs=False)
        with self.assertRaises(CrsError):
            inspect_asset(path, 'las')
        self.assertEqual(inspect_asset(path, 'las', 32643)['source_epsg'], 32643)
        path = cloud_file(self.root/'defined.las')
        with self.assertRaisesRegex(CrsError, 'conflicts'):
            inspect_asset(path, 'las', 4326)

    def test_raster_alignment_and_nodata(self):
        dsm = raster_file(self.root/'dsm.tif', nodata_pixel=True)
        dtm = raster_file(self.root/'dtm.tif', surface=False, resolution=2)
        meta = {'source_epsg':32643, 'local_zero_m':430}
        result = measure_rasters(dsm, dtm, meta, meta, self.parcel)
        self.assertAlmostEqual(result['height_m'], 9)
        self.assertAlmostEqual(result['ground_z'], 0)
        self.assertLess(result['coverage_fraction'], 1)

    def test_no_overlapping_valid_raster_data_fails(self):
        dsm = raster_file(self.root/'dsm.tif')
        dtm = raster_file(self.root/'dtm.tif', empty=True)
        meta = {'source_epsg':32643, 'local_zero_m':430}
        with self.assertRaisesRegex(CrsError, 'coverage'):
            measure_rasters(dsm, dtm, meta, meta, self.parcel)

    def test_utility_line_buffer_and_review_flag(self):
        feature = {'geometry':mapping(LineString([(0,0),(10,0)])),
                   'properties':{'local_code':'PIPE','su_class':'UTILITY','parent_code':'LOT',
                                 'diameter_m':0.6,'depth_m':3,'ground_z_m':0,'geom_origin':'SYNTHETIC'}}
        row = property_features([feature], None)[0]
        self.assertAlmostEqual(row['zmin'], -3.3)
        self.assertAlmostEqual(row['zmax'], -2.7)
        self.assertEqual(row['topology_status'], 'DEGRADED')
        self.assertIn('assumptions', row['construction'])

    def test_utility_z_coordinates_and_missing_or_sloping_depth(self):
        props = {'local_code':'PIPE','su_class':'UTILITY','parent_code':'LOT',
                 'diameter_m':0.6,'geom_origin':'SYNTHETIC'}
        good = {'geometry':mapping(LineString([(0,0,-3),(10,0,-3)])), 'properties':props}
        self.assertAlmostEqual(property_features([good], None)[0]['zmin'], -3.3)
        for points in ([(0,0),(10,0)], [(0,0,-3),(10,0,-5)]):
            with self.subTest(points=points), self.assertRaises(CrsError):
                property_features([{'geometry':mapping(LineString(points)), 'properties':props}], None)


if __name__ == '__main__':
    unittest.main()
