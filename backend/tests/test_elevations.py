from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import laspy
import numpy as np
from pyproj import CRS
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

    def test_unclassified_cloud_filters_adjacent_rough_returns(self):
        gx, gy = np.meshgrid(np.arange(0, 30, 0.5), np.arange(0, 20, 0.5))
        roof_x, roof_y = np.meshgrid(np.arange(2, 22, 0.25), np.arange(2, 12, 0.25))
        rough_x, rough_y = np.meshgrid(np.arange(22, 26, 0.25), np.arange(2, 12, 0.25))
        rough_z = np.where(np.arange(rough_x.size) % 2, 442, 448)
        x = np.concatenate([gx.ravel(), roof_x.ravel(), rough_x.ravel()]) + 500000
        y = np.concatenate([gy.ravel(), roof_y.ravel(), rough_y.ravel()]) + 2050000
        z = np.concatenate([np.full(gx.size, 430), np.full(roof_x.size, 439), rough_z])
        classes = np.concatenate([np.full(gx.size, 2), np.ones(roof_x.size + rough_x.size)])
        header = laspy.LasHeader(point_format=3, version='1.2')
        header.add_crs(CRS.from_epsg(32643))
        header.offsets = [500000, 2050000, 430]
        header.scales = [0.001, 0.001, 0.001]
        cloud = laspy.LasData(header)
        cloud.x, cloud.y, cloud.z = x, y, z
        cloud.classification = classes.astype('uint8')
        path = self.root/'rough_returns.las'
        cloud.write(path)
        result = measure_cloud(path, 32643, 430, self.parcel)
        self.assertEqual(result['method'], 'ground-plane-smooth-surface')
        self.assertAlmostEqual(result['height_m'], 9, places=2)
        self.assertLess(result['footprint'].bounds[2], 500023)

    def test_two_substantial_roofs_require_a_plan_or_smaller_parcel(self):
        gx, gy = np.meshgrid(np.arange(0, 30, 0.5), np.arange(0, 20, 0.5))
        a_x, a_y = np.meshgrid(np.arange(2, 14, 0.5), np.arange(2, 12, 0.5))
        b_x, b_y = np.meshgrid(np.arange(17, 29, 0.5), np.arange(2, 12, 0.5))
        x = np.concatenate([gx.ravel(), a_x.ravel(), b_x.ravel()]) + 500000
        y = np.concatenate([gy.ravel(), a_y.ravel(), b_y.ravel()]) + 2050000
        z = np.concatenate([np.full(gx.size, 430), np.full(a_x.size + b_x.size, 439)])
        classes = np.concatenate([np.full(gx.size, 2), np.full(a_x.size + b_x.size, 6)])
        header = laspy.LasHeader(point_format=3, version='1.2')
        header.add_crs(CRS.from_epsg(32643))
        header.offsets = [500000, 2050000, 430]
        header.scales = [0.001, 0.001, 0.001]
        cloud = laspy.LasData(header)
        cloud.x, cloud.y, cloud.z = x, y, z
        cloud.classification = classes.astype('uint8')
        path = self.root/'two_roofs.las'
        cloud.write(path)
        with self.assertRaisesRegex(CrsError, 'Multiple substantial building candidates'):
            measure_cloud(path, 32643, 430, self.parcel)

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
