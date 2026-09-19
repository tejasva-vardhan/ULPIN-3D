"""Task 5.2: explicit review of estimated (DEGRADED) geometry.

Opt in with TEST_DATABASE_URL pointing to an initialized, disposable
PostGIS database. Uses the same synthetic property_import fixture as
test_import_database.py, with requires_review flipped on selected
features to create DEGRADED estimates without needing the full
LAS/DSM pipeline.
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
from app.main import process_properties, issue_unit
from app.record import AmbiguousUnit, fetch_record
from app.review import record_review, review_history
from test_import import example



def _mark_review(raw, *codes):
    for feature in raw['features']:
        if feature['properties']['local_code'] in codes:
            feature['properties']['requires_review'] = True
    return raw


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'set TEST_DATABASE_URL to a disposable PostGIS database')
class ReviewDatabaseTests(unittest.TestCase):
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
            site = create_site(db, {'name': 'Review test', 'epsg': 32643,
                'parent_ulpin': parent, 'z_ref': 'LOCAL_SITE'})
            db.commit()
            return site

    def upload(self, raw, site=None):
        with self.session() as db:
            result = ingest_dataset(db, {'kind': 'floor_plans', 'filename': 'plans.geojson',
                'geojson': raw, 'epsg': 32643, 'site_id': (site or self.site)['id']}, Path('.'))
            db.commit()
            return result

    def tearDown(self):
        self.sessions.stop()
        self.transaction.rollback()
        self.conn.close()
        self.engine.dispose()

    def test_unreviewed_estimate_blocks_issuance_of_itself_and_descendants(self):
        raw = _mark_review(example(), 'B1')
        process_properties(UUID(self.upload(raw)['id']))
        with self.session() as db:
            self.assertEqual(fetch_record(db, 'B1', self.site['id'])['topology_status'], 'DEGRADED')
            self.assertEqual(fetch_record(db, 'U1', self.site['id'])['topology_status'], 'INVALID')
        for code in ('B1', 'U1', 'C1'):
            with self.assertRaises(HTTPException) as raised:
                issue_unit(code, UUID(self.site['id']))
            self.assertEqual(raised.exception.status_code, 409)

    def test_approval_without_release_does_not_touch_topology(self):
        raw = _mark_review(example(), 'B1')
        process_properties(UUID(self.upload(raw)['id']))
        with self.session() as db:
            row = record_review(db, {'local_code': 'B1', 'site_id': self.site['id'],
                'decision': 'APPROVED', 'reviewer_label': 'demo-reviewer',
                'reason': 'looks plausible from the photo'})
            self.assertEqual(row['topology_status'], 'DEGRADED')
            self.assertFalse(row['released_block'])
            self.assertIsNone(row['validation_run_id'])
            db.commit()
        with self.assertRaises(HTTPException) as raised:
            issue_unit('B1', UUID(self.site['id']))
        self.assertEqual(raised.exception.status_code, 409)

    def test_rejection_leaves_blocked_and_is_recorded(self):
        raw = _mark_review(example(), 'B1')
        process_properties(UUID(self.upload(raw)['id']))
        with self.session() as db:
            row = record_review(db, {'local_code': 'B1', 'site_id': self.site['id'],
                'decision': 'REJECTED', 'reviewer_label': 'demo-reviewer',
                'reason': 'footprint looks wrong', 'evidence_ref': 'photo://site-visit-1'})
            self.assertEqual(row['decision'], 'REJECTED')
            self.assertFalse(row['released_block'])
            self.assertEqual(row['topology_status'], 'DEGRADED')
            unit_id = row['spatial_unit_id']
            db.commit()
        with self.session() as db:
            history = review_history(db, {'spatial_unit_id': unit_id})
            self.assertEqual(history['count'], 1)
            self.assertEqual(history['reviews'][0]['decision'], 'REJECTED')
            self.assertEqual(history['reviews'][0]['evidence_ref'], 'photo://site-visit-1')
        with self.assertRaises(HTTPException) as raised:
            issue_unit('B1', UUID(self.site['id']))
        self.assertEqual(raised.exception.status_code, 409)

    def test_release_requires_approved_decision(self):
        raw = _mark_review(example(), 'B1')
        process_properties(UUID(self.upload(raw)['id']))
        with self.session() as db:
            with self.assertRaises(CrsError):
                record_review(db, {'local_code': 'B1', 'site_id': self.site['id'],
                    'decision': 'REJECTED', 'reviewer_label': 'demo-reviewer',
                    'release_review_block': True, 'reason': 'checked plan', 'evidence_ref': 'plan://test'})

    def test_supported_approval_releases_block_then_revalidates_and_allows_issuance(self):
        raw = _mark_review(example(), 'B1')
        process_properties(UUID(self.upload(raw)['id']))
        with self.session() as db:
            row = record_review(db, {'local_code': 'B1', 'site_id': self.site['id'],
                'decision': 'APPROVED', 'reviewer_label': 'demo-reviewer',
                'reason': 'matches the sanctioned plan', 'evidence_ref': 'plan://sanctioned-2024',
                'release_review_block': True})
            self.assertTrue(row['released_block'])
            self.assertIsNotNone(row['validation_run_id'])
            self.assertEqual(row['topology_status'], 'VALID')
            db.commit()
        with self.session() as db:
            self.assertEqual(fetch_record(db, 'U1', self.site['id'])['topology_status'], 'VALID')
        self.assertTrue(issue_unit('U1', UUID(self.site['id']))['issued'])

    def test_invalid_geometry_still_blocks_issuance_after_release(self):
        raw = example()
        raw['features'][4]['geometry'] = copy.deepcopy(raw['features'][3]['geometry'])  # overlap U1/U2
        raw = _mark_review(raw, 'B1')
        process_properties(UUID(self.upload(raw)['id']))
        with self.session() as db:
            record_review(db, {'local_code': 'B1', 'site_id': self.site['id'],
                'decision': 'APPROVED', 'reviewer_label': 'demo-reviewer',
                'release_review_block': True, 'reason': 'checked plan', 'evidence_ref': 'plan://test'})
            db.commit()
        with self.session() as db:
            self.assertEqual(fetch_record(db, 'B1', self.site['id'])['topology_status'], 'VALID')
            self.assertEqual(fetch_record(db, 'U1', self.site['id'])['topology_status'], 'INVALID')
        for code in ('B1',):
            self.assertTrue(issue_unit(code, UUID(self.site['id']))['issued'])
        with self.assertRaises(HTTPException) as raised:
            issue_unit('U1', UUID(self.site['id']))
        self.assertEqual(raised.exception.status_code, 409)

    def test_reviewing_one_unit_does_not_approve_siblings_or_parent(self):
        raw = _mark_review(example(), 'U1', 'U2')
        process_properties(UUID(self.upload(raw)['id']))
        with self.session() as db:
            self.assertEqual(fetch_record(db, 'B1', self.site['id'])['topology_status'], 'VALID')
            record_review(db, {'local_code': 'U1', 'site_id': self.site['id'],
                'decision': 'APPROVED', 'reviewer_label': 'demo-reviewer',
                'release_review_block': True, 'reason': 'checked plan', 'evidence_ref': 'plan://test'})
            db.commit()
        with self.session() as db:
            self.assertEqual(fetch_record(db, 'U1', self.site['id'])['topology_status'], 'VALID')
            self.assertEqual(fetch_record(db, 'U2', self.site['id'])['topology_status'], 'DEGRADED')
            self.assertEqual(fetch_record(db, 'B1', self.site['id'])['topology_status'], 'VALID')
        self.assertTrue(issue_unit('U1', UUID(self.site['id']))['issued'])
        with self.assertRaises(HTTPException) as raised:
            issue_unit('U2', UUID(self.site['id']))
        self.assertEqual(raised.exception.status_code, 409)

    def test_review_requires_active_unit_and_is_site_scoped(self):
        raw = _mark_review(example(), 'B1')
        process_properties(UUID(self.upload(raw)['id']))
        other = self.make_site('98ZY76XW54VU32')
        process_properties(UUID(self.upload(_mark_review(example(), 'B1'), site=other)['id']))
        with self.session() as db:
            with self.assertRaises(AmbiguousUnit):
                record_review(db, {'local_code': 'B1', 'decision': 'APPROVED',
                    'reviewer_label': 'demo-reviewer', 'release_review_block': True, 'reason': 'checked plan', 'evidence_ref': 'plan://test'})
            with self.assertRaisesRegex(CrsError, 'no active spatial unit'):
                record_review(db, {'local_code': 'NOPE', 'site_id': self.site['id'],
                    'decision': 'APPROVED', 'reviewer_label': 'demo-reviewer', 'reason':'checked'})
            with self.assertRaisesRegex(CrsError, 'reviewer_label'):
                record_review(db, {'local_code': 'B1', 'site_id': self.site['id'], 'decision': 'APPROVED'})

    def test_review_history_persists_multiple_decisions_in_order(self):
        raw = _mark_review(example(), 'B1')
        process_properties(UUID(self.upload(raw)['id']))
        with self.session() as db:
            first = record_review(db, {'local_code': 'B1', 'site_id': self.site['id'],
                'decision': 'REJECTED', 'reviewer_label': 'reviewer-1', 'reason': 'not yet'})
            second = record_review(db, {'local_code': 'B1', 'site_id': self.site['id'],
                'decision': 'APPROVED', 'reviewer_label': 'reviewer-2',
                'release_review_block': True, 'reason': 'checked plan', 'evidence_ref': 'plan://test'})
            db.commit()
        with self.session() as db:
            history = review_history(db, {'spatial_unit_id': second['spatial_unit_id']})
        self.assertEqual(history['count'], 2)
        self.assertEqual([r['decision'] for r in history['reviews']], ['REJECTED', 'APPROVED'])
        self.assertEqual(history['reviews'][0]['id'], first['id'])

    def test_rejection_after_approval_blocks_unit_and_children(self):
        process_properties(UUID(self.upload(_mark_review(example(), 'B1'))['id']))
        base = {'local_code':'B1', 'site_id':self.site['id'], 'reviewer_label':'tester',
                'reason':'checked evidence', 'evidence_ref':'plan://test'}
        with self.session() as db:
            record_review(db, {**base, 'decision':'APPROVED', 'release_review_block':True})
            db.commit()
        self.assertTrue(issue_unit('U1', UUID(self.site['id']))['issued'])
        with self.session() as db:
            result = record_review(db, {**base, 'decision':'REJECTED'})
            self.assertEqual(result['topology_status'], 'DEGRADED')
            self.assertIsNotNone(result['validation_run_id'])
            db.commit()
        for code in ('B1','U1'):
            with self.assertRaises(HTTPException) as caught:
                issue_unit(code, UUID(self.site['id']))
            self.assertEqual(caught.exception.status_code, 409)

    def test_review_input_must_be_explicit_and_supported(self):
        process_properties(UUID(self.upload(_mark_review(example(), 'U1'))['id']))
        base = {'local_code':'U1','site_id':self.site['id'],'decision':'APPROVED',
                'reviewer_label':'tester','reason':'checked','evidence_ref':'plan://test'}
        for extra in ({'release_review_block':'false'}, {'release_review_block':1},
                      {'release_review_block':True,'evidence_ref':' '}, {'reason':''}):
            with self.session() as db:
                with self.assertRaises(CrsError):
                    record_review(db, {**base, **extra})
        with self.session() as db:
            rec = fetch_record(db,'U1',self.site['id'])
            self.assertEqual(rec['reviews'], [])
            self.assertEqual(rec['topology_status'],'DEGRADED')

    def test_child_approval_does_not_release_unreviewed_ancestor(self):
        process_properties(UUID(self.upload(_mark_review(example(), 'B1','U1'))['id']))
        with self.session() as db:
            record_review(db, {'local_code':'U1','site_id':self.site['id'],'decision':'APPROVED',
                'reviewer_label':'tester','reason':'checked','evidence_ref':'plan://test',
                'release_review_block':True})
            self.assertEqual(fetch_record(db,'B1',self.site['id'])['topology_status'],'DEGRADED')
            db.commit()
        with self.assertRaises(HTTPException):
            issue_unit('U1',UUID(self.site['id']))


if __name__ == '__main__':
    unittest.main()
