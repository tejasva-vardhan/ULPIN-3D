import copy
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException
from pyproj import Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.geo import CrsError
from app.ingest import create_site, ingest_dataset, ImportConflict
from app.main import process_properties, issue_unit, get_unit, list_units
from app.properties import process_dataset
from app.record import fetch_record, supersede_new_version, AmbiguousUnit
from app.seed import seed_demo, degrade_without_plans
from test_import import example


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'set TEST_DATABASE_URL to a disposable PostGIS database')
class ImportDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(os.environ['TEST_DATABASE_URL'])
        self.conn = self.engine.connect()
        self.transaction = self.conn.begin()
        self.sessions = patch('app.main.SessionLocal', self.session)
        self.sessions.start()
        self.site = self.make_site('12AB34CD56EF78')

    def session(self):
        return Session(bind=self.conn, join_transaction_mode='create_savepoint')

    def make_site(self, parent):
        with self.session() as db:
            site = create_site(db, {'name':'Synthetic import test','epsg':32643,
                'parent_ulpin':parent,'z_ref':'LOCAL_SITE'})
            db.commit()
            return site

    def upload(self, raw=None, site=None, epsg=32643):
        with self.session() as db:
            result = ingest_dataset(db, {'kind':'floor_plans','filename':'plans.geojson',
                'geojson': raw if raw is not None else example(), 'epsg':epsg,
                'site_id':(site or self.site)['id']}, Path('.'))
            db.commit()
            return result

    def tearDown(self):
        self.sessions.stop()
        self.transaction.rollback()
        self.conn.close()
        self.engine.dispose()

    def test_import_process_and_issue_preserve_source_and_separate_units(self):
        source = self.upload()
        result = process_properties(UUID(source['id']))
        self.assertEqual(result['count'], 6)
        self.assertEqual(result['extruded_solids'], 6)
        units = list_units(UUID(self.site['id']))['units']
        self.assertEqual(len(units), 6)
        self.assertTrue(all(u['topology_status'] == 'VALID' for u in units))
        self.assertTrue(all(u['display_id'].startswith('UNISSUED/') for u in units))
        with self.session() as db:
            rec = fetch_record(db, 'U1', self.site['id'])
            self.assertAlmostEqual(rec['volume_m3'], 270.0, places=5)
            self.assertEqual(rec['source']['feature']['id'], 'U1')
            self.assertEqual(rec['source']['feature']['properties']['name'], 'West apartment')
            self.assertEqual(rec['source']['checksum_sha256'], source['checksum_sha256'])
        self.assertTrue(issue_unit('U1', UUID(self.site['id']))['issued'])

    def test_retries_reuse_ids_and_changed_input_conflicts(self):
        source = self.upload()
        first = process_properties(UUID(source['id']))
        self.assertEqual(self.upload()['id'], source['id'])
        second = process_properties(UUID(source['id']))
        self.assertTrue(second['reused'])
        self.assertEqual(first['unit_ids'], second['unit_ids'])
        changed = example()
        changed['features'][3]['properties']['name'] = 'Edited'
        other = self.upload(changed)
        with self.assertRaises(ImportConflict):
            process_properties(UUID(other['id']))
        self.assertEqual(list_units(UUID(self.site['id']))['count'], 6)

    def test_invalid_late_feature_rolls_back_entire_processing(self):
        raw = example()
        raw['features'][-1]['properties']['zmax'] = -1
        source = self.upload(raw)
        with self.assertRaises(HTTPException) as raised:
            process_properties(UUID(source['id']))
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(list_units(UUID(self.site['id']))['count'], 0)
        processed = self.conn.execute(text("SELECT meta->'processed_unit_ids' FROM source_dataset WHERE id=:id"), {'id':source['id']}).scalar_one()
        self.assertIsNone(processed)

    def test_parent_order_and_separate_floor_plan_dataset(self):
        raw = example()
        parcel = {**raw, 'features':raw['features'][:1]}
        plans = {**raw, 'features':list(reversed(raw['features'][1:]))}
        process_properties(UUID(self.upload(parcel)['id']))
        result = process_properties(UUID(self.upload(plans)['id']))
        self.assertEqual(result['count'], 5)
        self.assertEqual(list_units(UUID(self.site['id']))['count'], 6)
        counts = self.conn.execute(text("""
            SELECT count(*) FROM floor f JOIN spatial_unit s ON s.id=f.spatial_unit_id WHERE s.site_id=:site
        """), {'site':self.site['id']}).scalar_one()
        self.assertEqual(counts, 1)

    def test_missing_or_cyclic_parent_rejected(self):
        for parent in ('UNKNOWN', 'U1'):
            raw = example()
            raw['features'][3]['properties']['parent_code'] = parent
            source = self.upload(raw)
            with self.assertRaises(HTTPException) as raised:
                process_properties(UUID(source['id']))
            self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(list_units(UUID(self.site['id']))['count'], 0)

    def test_reprojects_geographic_input(self):
        raw = example()
        convert = Transformer.from_crs(32643, 4326, always_xy=True).transform
        for feature in raw['features']:
            feature['geometry'] = mapping(transform(convert, shape(feature['geometry'])))
        source = self.upload(raw, epsg=4326)
        process_properties(UUID(source['id']))
        with self.session() as db:
            rec = fetch_record(db, 'U1', self.site['id'])
            self.assertAlmostEqual(rec['volume_m3'], 270, places=4)
            self.assertEqual(rec['source']['epsg'], 4326)

    def test_site_scoping_prevents_ambiguous_read_and_issue(self):
        process_properties(UUID(self.upload()['id']))
        other = self.make_site('98ZY76XW54VU32')
        process_properties(UUID(self.upload(site=other)['id']))
        with self.assertRaises(AmbiguousUnit):
            get_unit('U1')
        with self.assertRaises(AmbiguousUnit):
            issue_unit('U1')
        self.assertTrue(issue_unit('U1', UUID(other['id']))['issued'])
        self.assertEqual(get_unit('U1', UUID(other['id']))['parent_ulpin'], other['parent_ulpin'])

    def test_topology_failure_persists_but_cannot_issue(self):
        raw = example()
        raw['features'][4]['geometry'] = copy.deepcopy(raw['features'][3]['geometry'])
        result = process_properties(UUID(self.upload(raw)['id']))
        self.assertEqual(result['count'], 6)
        for code in ('U1', 'U2'):
            with self.assertRaises(HTTPException) as raised:
                issue_unit(code, UUID(self.site['id']))
            self.assertEqual(raised.exception.status_code, 409)

    def test_source_links_survive_versioning_and_demo_cannot_reset_imports(self):
        source = self.upload()
        process_properties(UUID(source['id']))
        with self.session() as db:
            supersede_new_version(db, 'U1', self.site['id'])
            rec = fetch_record(db, 'U1', self.site['id'])
            self.assertEqual(rec['version'], 2)
            self.assertEqual(rec['source_dataset_id'], source['id'])
            self.assertEqual(rec['site_id'], self.site['id'])
            with self.assertRaises(ImportConflict):
                seed_demo(db)
            db.commit()


    def test_exports_and_parent_links_are_site_scoped(self):
        import json
        from app.main import export_geojson, export_citygml
        process_properties(UUID(self.upload()['id']))
        other = self.make_site('98ZY76XW54VU32')
        process_properties(UUID(self.upload(site=other)['id']))
        rows = list_units(UUID(self.site['id']))['units']
        building = next(r for r in rows if r['su_class']=='BUILDING')
        floor = next(r for r in rows if r['su_class']=='FLOOR')
        self.assertEqual(floor['parent_id'], building['uuid'])
        exported = json.loads(export_geojson(UUID(self.site['id'])).body)
        self.assertEqual(len(exported['features']),6)
        self.assertEqual({f['properties']['site_id'] for f in exported['features']},{self.site['id']})
        xml = export_citygml(UUID(self.site['id']),UUID(building['uuid'])).body.decode()
        self.assertIn(self.site['parent_ulpin'],xml)
        self.assertNotIn('Synthetic Kothrud',xml)
        with self.assertRaises(HTTPException) as caught:
            export_citygml(UUID(other['id']),UUID(building['uuid']))
        self.assertEqual(caught.exception.status_code,404)

if __name__ == '__main__':
    unittest.main()
