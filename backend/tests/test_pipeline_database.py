import asyncio
import copy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException
from shapely.geometry import LineString, mapping
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.config import settings
from app.geo import CrsError
from app.ingest import create_site, ingest_dataset
from app.main import process_building, process_properties, upload_elevation, issue_unit, list_units
from app.pipeline.assets import register_asset
from app.pipeline.workflow import BuildingRequest
from app.record import fetch_record
from elevation_fixtures import cloud_file, raster_file
from test_import import example


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'set TEST_DATABASE_URL to a disposable PostGIS database')
class PipelineDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(os.environ['TEST_DATABASE_URL'])
        self.conn = self.engine.connect()
        self.transaction = self.conn.begin()
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.assets = patch.object(settings, 'upload_dir', self.temp.name)
        self.assets.start()
        self.sessions = patch('app.main.SessionLocal', self.session)
        self.sessions.start()
        with self.session() as db:
            self.site = create_site(db, {'name':'Elevation test','epsg':32643,'parent_ulpin':'12AB34CD56EF78'})
            db.commit()
        raw = example()
        raw['features'] = raw['features'][:1]
        process_properties(UUID(self.vector(raw)['id']))

    def session(self):
        return Session(bind=self.conn, join_transaction_mode='create_savepoint')

    def vector(self, raw):
        with self.session() as db:
            result = ingest_dataset(db, {'kind':'plans','geojson':raw,'epsg':32643,'site_id':self.site['id']}, self.root)
            db.commit()
            return result

    def asset(self, kind='las', **kwargs):
        path = self.root / ('cloud.las' if kind == 'las' else kind+'.tif')
        if kind == 'las':
            cloud_file(path)
        else:
            raster_file(path, surface=kind == 'dsm', resolution=1 if kind == 'dsm' else 2)
        with self.session() as db:
            result = register_asset(db, path, site_id=UUID(self.site['id']), kind=kind,
                filename=path.name, geom_origin='SYNTHETIC', z_ref='ORTHOMETRIC_EGM',
                local_zero_m=kwargs.get('local_zero_m', 430))
            db.commit()
            return result

    def request(self, **kwargs):
        return BuildingRequest(site_id=self.site['id'], parcel_code='LOT', building_code='B1', **kwargs)

    def tearDown(self):
        self.sessions.stop()
        self.assets.stop()
        self.transaction.rollback()
        self.conn.close()
        self.engine.dispose()
        self.temp.cleanup()

    def test_cloud_pipeline_persists_review_required_floors_and_retries(self):
        source = self.asset()
        payload = self.request(point_cloud_id=source['id'])
        result = process_building(payload)
        self.assertEqual(result['count'], 4)  # building plus three proposed floors; no invented apartments
        self.assertAlmostEqual(result['metrics']['height_m'], 9, places=3)
        units = [u for u in list_units(UUID(self.site['id']))['units'] if u['su_class'] != 'PARCEL']
        self.assertTrue(all(u['topology_status'] == 'DEGRADED' for u in units))
        self.assertTrue(all(u['display_id'].startswith('UNISSUED/') for u in units))
        self.assertEqual(process_building(payload)['unit_ids'], result['unit_ids'])
        with self.assertRaises(HTTPException) as raised:
            issue_unit('B1', UUID(self.site['id']))
        self.assertEqual(raised.exception.status_code, 409)
        with self.session() as db:
            rec = fetch_record(db, 'B1', self.site['id'])
            self.assertEqual(rec['source']['processing']['inputs'][0]['checksum_sha256'], source['checksum_sha256'])

    def test_raster_pipeline(self):
        dsm, dtm = self.asset('dsm'), self.asset('dtm')
        result = process_building(self.request(dsm_id=dsm['id'], dtm_id=dtm['id'], storeys=3))
        self.assertEqual(result['count'], 4)
        self.assertAlmostEqual(result['metrics']['height_m'], 9)
        self.assertEqual(result['metrics']['method'], 'aligned-dsm-minus-dtm')

    def test_plans_take_precedence_over_measured_height(self):
        raw = example()
        raw['features'] = raw['features'][1:]
        plans = self.vector(raw)
        result = process_building(self.request(point_cloud_id=self.asset()['id'], plan_dataset_id=plans['id']))
        self.assertTrue(result['metrics']['plans_preserved'])
        self.assertEqual(result['metrics']['plan_source']['checksum_sha256'], plans['checksum_sha256'])
        self.assertAlmostEqual(result['metrics']['height_difference_from_plan_m'], 6, places=3)
        with self.session() as db:
            rec = fetch_record(db, 'U1', self.site['id'])
            self.assertEqual(rec['zmax'], 3)  # source cloud roof is ~9 m, but supplied plan remains authoritative input
            self.assertEqual(rec['source_dataset_id'], plans['id'])

    def test_changed_asset_and_cross_site_source_rejected(self):
        source = self.asset()
        payload = self.request(point_cloud_id=source['id'])
        path = self.root / source['meta']['asset_name']
        original = path.read_bytes()
        path.write_bytes(original + b'changed')
        with self.assertRaisesRegex(CrsError, 'checksum'):
            process_building(payload)
        path.write_bytes(original)
        self.conn.execute(text('UPDATE source_dataset SET site_id=NULL WHERE id=:id'), {'id':source['id']})
        with self.assertRaisesRegex(CrsError, 'belong'):
            process_building(payload)
        self.assertEqual(list_units(UUID(self.site['id']))['count'], 1)

    def test_nonlocal_elevations_require_explicit_zero(self):
        with self.assertRaisesRegex(CrsError, 'local_zero_m'):
            self.asset(local_zero_m=None)

    def test_utility_centreline_becomes_corridor_with_original_source(self):
        raw = {'type':'Feature','id':'water','geometry':mapping(LineString([(500002,2050001),(500022,2050001)])),
               'properties':{'local_code':'WATER','parent_code':'LOT','su_class':'UTILITY',
                             'diameter_m':0.6,'ground_z_m':0,'depth_m':3,'geom_origin':'SYNTHETIC'}}
        source = self.vector(raw)
        result = process_properties(UUID(source['id']))
        self.assertEqual(result['count'], 1)
        with self.session() as db:
            rec = fetch_record(db, 'WATER', self.site['id'])
            self.assertAlmostEqual(rec['volume_m3'], 7.2, places=4)
            self.assertEqual(rec['source']['feature']['geometry']['type'], 'LineString')
            self.assertEqual(rec['source']['construction']['method'], 'constant-height buffered prism')
            self.assertEqual(rec['topology_status'], 'DEGRADED')

    def test_upload_stream_reuse_and_failure_cleanup(self):
        input_path = cloud_file(self.root/'original.las')
        content = input_path.read_bytes()
        async def upload(body):
            async def receive():
                return {'type':'http.request','body':body,'more_body':False}
            request = Request({'type':'http','method':'POST','headers':[]}, receive)
            return await upload_elevation(request, site_id=UUID(self.site['id']), kind='las',
                filename='external.las', geom_origin='SYNTHETIC', z_ref='ORTHOMETRIC_EGM', local_zero_m=430)
        first = asyncio.run(upload(content))
        second = asyncio.run(upload(content))
        self.assertEqual(first['id'], second['id'])
        self.assertTrue(second['reused'])
        self.assertEqual(len(list(self.root.iterdir())), 2)
        with self.assertRaises(CrsError):
            asyncio.run(upload(b'not a LAS file'))
        self.assertEqual(len(list(self.root.iterdir())), 2)
        with patch.object(settings, 'max_upload_bytes', 1), self.assertRaises(HTTPException) as raised:
            asyncio.run(upload(content))
        self.assertEqual(raised.exception.status_code, 413)
        self.assertEqual(len(list(self.root.iterdir())), 2)


if __name__ == '__main__':
    unittest.main()
