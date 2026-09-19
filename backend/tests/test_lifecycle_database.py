"""Task 5.3: preserve property lifecycle and history (versioning + withdrawal).

Opt in with TEST_DATABASE_URL pointing to an initialized, disposable
PostGIS database.
"""

import copy
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.geo import CrsError
from app.ingest import create_site, ingest_dataset
from app.main import process_properties, issue_unit, new_unit_version, post_withdraw, list_unit_versions
from app.record import AmbiguousUnit, fetch_record
from app.review import record_review, review_history
from app.rights import create_baunit, create_party, create_rrr
from test_import import example



@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'set TEST_DATABASE_URL to a disposable PostGIS database')
class LifecycleDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(os.environ['TEST_DATABASE_URL'])
        self.conn = self.engine.connect()
        self.transaction = self.conn.begin()
        self.sessions = patch('app.main.SessionLocal', self.session)
        self.sessions.start()
        self.site = self.make_site('12AB34CD56EF78')
        process_properties(UUID(self.upload()['id']))

    def session(self):
        return Session(bind=self.conn, join_transaction_mode='create_savepoint')

    def make_site(self, parent):
        with self.session() as db:
            site = create_site(db, {'name': 'Lifecycle test', 'epsg': 32643,
                'parent_ulpin': parent, 'z_ref': 'LOCAL_SITE'})
            db.commit()
            return site

    def upload(self, raw=None):
        with self.session() as db:
            result = ingest_dataset(db, {'kind': 'floor_plans', 'filename': 'plans.geojson',
                'geojson': raw if raw is not None else example(), 'epsg': 32643,
                'site_id': self.site['id']}, Path('.'))
            db.commit()
            return result

    def tearDown(self):
        self.sessions.stop()
        self.transaction.rollback()
        self.conn.close()
        self.engine.dispose()

    def test_new_version_is_unissued_until_explicit_issue(self):
        self.assertTrue(issue_unit('U1', UUID(self.site['id']))['issued'])
        result = new_unit_version('U1', UUID(self.site['id']))
        self.assertTrue(result['new_display'].startswith('UNISSUED/'))
        self.assertEqual(result['new_topology_status'], 'VALID')
        with self.session() as db:
            rec = fetch_record(db, 'U1', self.site['id'])
            self.assertEqual(rec['version'], 2)
            self.assertTrue(rec['display_id'].startswith('UNISSUED/'))
        self.assertTrue(issue_unit('U1', UUID(self.site['id']))['issued'])
        with self.session() as db:
            rec = fetch_record(db, 'U1', self.site['id'])
            self.assertTrue(rec['display_id'].startswith('IN-ULPIN3D/'))

    def test_new_version_preserves_rights_but_not_review_history(self):
        with self.session() as db:
            party = create_party(db, {'party_type': 'person', 'name': 'Allottee'})
            baunit = create_baunit(db, {'name': 'Scheme A'})
            create_rrr(db, {'baunit_id': baunit['id'], 'party_id': party['id'],
                'site_id': self.site['id'], 'local_code': 'U1', 'rrr_type': 'RIGHT', 'share': 0.7})
            db.commit()
        result = new_unit_version('U1', UUID(self.site['id']))
        with self.session() as db:
            new_rec = fetch_record(db, 'U1', self.site['id'])
            self.assertEqual(len(new_rec['rrr']), 1)
            self.assertAlmostEqual(new_rec['rrr'][0]['share'], 0.7)
            self.assertEqual(new_rec['reviews'], [])
            old_rows = db.execute(text("""
                SELECT status, status_reason FROM spatial_unit WHERE id = :id
            """), {'id': result['superseded_uuid']}).mappings().one()
            self.assertEqual(old_rows['status'], 'SUPERSEDED')
            self.assertEqual(old_rows['status_reason'], 'superseded by new version')
            old_rrr_count = db.execute(text("""
                SELECT count(*) FROM rrr WHERE spatial_unit_id = :id
            """), {'id': result['superseded_uuid']}).scalar_one()
            self.assertEqual(old_rrr_count, 1)  # old version's own RRR rows are preserved, not moved

    def test_versioning_refused_while_active_children_exist(self):
        with self.assertRaises(HTTPException) as raised:
            new_unit_version('F1', UUID(self.site['id']))
        self.assertEqual(raised.exception.status_code, 409)
        with self.session() as db:
            rec = fetch_record(db, 'F1', self.site['id'])
            self.assertEqual(rec['version'], 1)

    def test_versioning_requires_valid_topology(self):
        raw = example()
        raw['features'] = [copy.deepcopy(raw['features'][3])]
        raw['features'][0]['properties']['local_code'] = 'OVERLAP'
        raw['features'][0]['id'] = 'OVERLAP'
        process_properties(UUID(self.upload(raw)['id']))
        with self.assertRaises(HTTPException) as raised:
            new_unit_version('U1', UUID(self.site['id']))
        self.assertEqual(raised.exception.status_code, 409)

    def test_withdrawal_sets_extinguished_with_reason_and_stays_inspectable(self):
        result = post_withdraw('U1', {'reason': 'unit demolished', 'actor_label': 'ops-team'},
                                UUID(self.site['id']))
        self.assertEqual(result['reason'], 'unit demolished')
        versions = list_unit_versions('U1', UUID(self.site['id']))
        self.assertEqual(versions['count'], 1)
        self.assertEqual(versions['versions'][0]['status'], 'EXTINGUISHED')
        self.assertEqual(versions['versions'][0]['status_reason'], 'unit demolished')
        self.assertEqual(versions['versions'][0]['status_actor'], 'ops-team')
        with self.assertRaises(HTTPException) as raised:
            issue_unit('U1', UUID(self.site['id']))
        self.assertEqual(raised.exception.status_code, 404)

    def test_withdrawal_requires_a_reason(self):
        with self.assertRaises(HTTPException) as raised:
            post_withdraw('U1', {}, UUID(self.site['id']))
        with self.assertRaises(HTTPException) as raised:
            post_withdraw('U1', {'reason': '   '}, UUID(self.site['id']))

    def test_withdrawal_refused_while_active_children_exist(self):
        with self.assertRaises(HTTPException) as raised:
            post_withdraw('F1', {'reason': 'floor removed'}, UUID(self.site['id']))
        self.assertEqual(raised.exception.status_code, 409)
        with self.session() as db:
            rec = fetch_record(db, 'F1', self.site['id'])
            self.assertEqual(rec['status'], 'ACTIVE')

    def test_duplicate_withdrawal_is_not_found_second_time(self):
        post_withdraw('U1', {'reason': 'first withdrawal'}, UUID(self.site['id']))
        with self.assertRaises(HTTPException) as raised:
            post_withdraw('U1', {'reason': 'second attempt'}, UUID(self.site['id']))
        self.assertEqual(raised.exception.status_code, 404)

    def test_withdrawing_overlapping_duplicate_revalidates_remaining_unit(self):
        raw = example()
        dup = copy.deepcopy(raw['features'][3])
        dup['id'] = 'U1-DUP'
        dup['properties'] = {**dup['properties'], 'local_code': 'U1-DUP'}
        raw['features'] = [dup]
        process_properties(UUID(self.upload(raw)['id']))
        with self.session() as db:
            self.assertEqual(fetch_record(db, 'U1', self.site['id'])['topology_status'], 'INVALID')
            self.assertEqual(fetch_record(db, 'U1-DUP', self.site['id'])['topology_status'], 'INVALID')
        post_withdraw('U1-DUP', {'reason': 'seeded duplicate, withdrawn for the demo'}, UUID(self.site['id']))
        with self.session() as db:
            self.assertEqual(fetch_record(db, 'U1', self.site['id'])['topology_status'], 'VALID')
        self.assertTrue(issue_unit('U1', UUID(self.site['id']))['issued'])

    def test_estimated_version_needs_its_own_review_and_keeps_history(self):
        with self.session() as db:
            db.execute(text("UPDATE spatial_unit SET topology_status='DEGRADED', review_required=true WHERE site_id=:site AND local_code='U1'"), {'site':self.site['id']})
            record_review(db, {'local_code':'U1','site_id':self.site['id'],'decision':'APPROVED',
                'reviewer_label':'tester','reason':'checked','evidence_ref':'plan://test','release_review_block':True})
            db.commit()
        result = new_unit_version('U1',UUID(self.site['id']))
        self.assertEqual(result['new_topology_status'],'DEGRADED')
        with self.assertRaises(HTTPException):
            issue_unit('U1',UUID(self.site['id']))
        with self.session() as db:
            old = fetch_record(db,spatial_unit_id=result['superseded_uuid'])
            new = fetch_record(db,spatial_unit_id=result['new_uuid'])
            self.assertEqual(len(old['reviews']),1)
            self.assertEqual(new['reviews'],[])
            self.assertEqual(new['source'],old['source'])
            record_review(db, {'spatial_unit_id':result['new_uuid'],'decision':'APPROVED',
                'reviewer_label':'tester','reason':'rechecked','evidence_ref':'plan://v2','release_review_block':True})
            db.commit()
        self.assertTrue(issue_unit('U1',UUID(self.site['id']))['issued'])
        post_withdraw('U1',{'reason':'withdrawn'},UUID(self.site['id']))
        with self.session() as db:
            retired = fetch_record(db,spatial_unit_id=result['new_uuid'])
            self.assertEqual(retired['status'],'EXTINGUISHED')
            self.assertEqual(len(retired['reviews']),1)

    def test_empty_floor_version_preserves_floor_metadata(self):
        for code in ('U1','U2','C1'):
            post_withdraw(code,{'reason':'withdrawn'},UUID(self.site['id']))
        result = new_unit_version('F1',UUID(self.site['id']))
        with self.session() as db:
            floor = db.execute(text('SELECT level_index FROM floor WHERE spatial_unit_id=:id'),
                               {'id':result['new_uuid']}).scalar_one()
            self.assertEqual(floor,1)


if __name__ == '__main__':
    unittest.main()
