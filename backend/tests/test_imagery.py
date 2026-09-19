"""Small authored RGB tiles verify drone imagery ingestion, not image accuracy."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import UUID

import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box, mapping
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.geo import CrsError
from app.imagery import inspect_orthophoto, orthophoto_path, register_orthophoto
from app.ingest import create_site


def photo(path, *, bands=3, crs='EPSG:32643', west=500000):
    values = np.zeros((bands, 20, 30), dtype='uint8')
    with rasterio.open(path, 'w', driver='GTiff', width=30, height=20,
                       count=bands, dtype='uint8', crs=crs,
                       transform=from_origin(west, 2050020, 1, 1)) as image:
        image.write(values)
    return path


class ImageryInputTests(unittest.TestCase):
    def test_georeferenced_rgb_bounds_and_crs_are_required(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            good = photo(root/'good.tif')
            info = inspect_orthophoto(good)
            self.assertEqual(info['bands'], 3)
            self.assertEqual(info['source_epsg'], 32643)
            self.assertAlmostEqual(info['bounds_32643'][0], 500000)
            with self.assertRaisesRegex(CrsError, 'conflicts'):
                inspect_orthophoto(good, 4326)
            with self.assertRaisesRegex(CrsError, 'three- or four-band'):
                inspect_orthophoto(photo(root/'mono.tif', bands=1))
            with self.assertRaisesRegex(CrsError, 'CRS missing'):
                inspect_orthophoto(photo(root/'no-crs.tif', crs=None))


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'set TEST_DATABASE_URL to a disposable PostGIS database')
class ImageryDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = create_engine(os.environ['TEST_DATABASE_URL'])
        self.conn = self.engine.connect()
        self.transaction = self.conn.begin()
        self.db = Session(bind=self.conn, join_transaction_mode='create_savepoint')
        self.site = create_site(self.db, {'name': 'Orthophoto test', 'epsg': 32643,
            'parent_ulpin': '12AB34CD56EF78',
            'bbox_geojson': mapping(box(500000, 2050000, 500030, 2050020))})
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.transaction.rollback()
        self.conn.close()
        self.engine.dispose()
        self.temp.cleanup()

    def test_register_reuse_and_checksum_protected_read(self):
        path = photo(self.root/'photo.tif')
        first = register_orthophoto(self.db, path, site_id=UUID(self.site['id']),
                                    filename='photo.tif')
        self.assertFalse(first['reused'])
        self.assertEqual(first['kind'], 'drone-orthophoto')
        self.assertEqual(len(first['checksum_sha256']), 64)
        self.assertTrue(register_orthophoto(self.db, path, site_id=UUID(self.site['id']),
                                             filename='photo.tif')['reused'])
        source_path, source = orthophoto_path(self.db, UUID(first['id']), self.root)
        self.assertEqual(source_path, path)
        self.assertEqual(source['meta']['bounds_32643'][0], 500000)
        self.assertTrue(source['meta']['site_boundary_checked'])
        path.write_bytes(path.read_bytes() + b'changed')
        with self.assertRaisesRegex(CrsError, 'checksum'):
            orthophoto_path(self.db, UUID(first['id']), self.root)

    def test_rejects_image_outside_site(self):
        path = photo(self.root/'elsewhere.tif', west=510000)
        with self.assertRaisesRegex(CrsError, 'does not intersect'):
            register_orthophoto(self.db, path, site_id=UUID(self.site['id']),
                                filename='elsewhere.tif')


if __name__ == '__main__':
    unittest.main()
