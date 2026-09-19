"""Task 5.1: rights recording against imported properties.

Opt in with TEST_DATABASE_URL pointing to an initialized, disposable
PostGIS database. Each test runs in a rolled-back transaction/savepoint,
matching the convention in test_import_database.py.
"""

import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.geo import CrsError
from app.ingest import create_site, ingest_dataset, ImportConflict
from app.main import process_properties
from app.record import AmbiguousUnit, fetch_record
from app.rights import create_baunit, create_party, create_rrr, link_baunit, list_rrr
from test_import import example

# Additive DDL for task 5, mirroring app.db.ensure_schema(); applied defensively
# in setUp so these tests do not depend on whether the disposable database was
# (re)initialized from the updated backend/sql/init.sql.


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'set TEST_DATABASE_URL to a disposable PostGIS database')
class RightsDatabaseTests(unittest.TestCase):
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
            site = create_site(db, {'name': 'Rights test', 'epsg': 32643,
                'parent_ulpin': parent, 'z_ref': 'LOCAL_SITE'})
            db.commit()
            return site

    def upload(self, raw=None, site=None):
        with self.session() as db:
            result = ingest_dataset(db, {'kind': 'floor_plans', 'filename': 'plans.geojson',
                'geojson': raw if raw is not None else example(), 'epsg': 32643,
                'site_id': (site or self.site)['id']}, Path('.'))
            db.commit()
            return result

    def tearDown(self):
        self.sessions.stop()
        self.transaction.rollback()
        self.conn.close()
        self.engine.dispose()

    def unit_uuid(self, code, site=None):
        with self.session() as db:
            return fetch_record(db, code, (site or self.site)['id'])['uuid']

    def test_rrr_recorded_against_imported_unit_and_readable(self):
        with self.session() as db:
            party = create_party(db, {'party_type': 'person', 'name': 'Allottee'})
            baunit = create_baunit(db, {'name': 'Scheme A'})
            row = create_rrr(db, {'baunit_id': baunit['id'], 'party_id': party['id'],
                'site_id': self.site['id'], 'local_code': 'U1', 'rrr_type': 'RIGHT',
                'share': 0.5, 'description': 'half share', 'evidence_ref': 'doc://sale-deed-1'})
            self.assertEqual(row['claim_status'], 'CLAIMED')
            self.assertTrue(row['not_legal_title'])
            db.commit()
        with self.session() as db:
            rec = fetch_record(db, 'U1', self.site['id'])
            self.assertEqual(len(rec['rrr']), 1)
            self.assertEqual(rec['rrr'][0]['evidence_ref'], 'doc://sale-deed-1')
            self.assertEqual(rec['rrr'][0]['claim_status'], 'CLAIMED')
            rows = list_rrr(db, self.site['id'])
            self.assertEqual(len(rows), 1)

    def test_invalid_references_are_rejected(self):
        with self.session() as db:
            party = create_party(db, {'party_type': 'person', 'name': 'Allottee'})
            baunit = create_baunit(db, {'name': 'Scheme A'})
            with self.assertRaisesRegex(CrsError, 'party_id'):
                create_rrr(db, {'baunit_id': baunit['id'], 'party_id': '00000000-0000-0000-0000-000000000000',
                    'site_id': self.site['id'], 'local_code': 'U1', 'rrr_type': 'RIGHT', 'share': 0.5})
            with self.assertRaisesRegex(CrsError, 'baunit_id'):
                create_rrr(db, {'baunit_id': '00000000-0000-0000-0000-000000000000', 'party_id': party['id'],
                    'site_id': self.site['id'], 'local_code': 'U1', 'rrr_type': 'RIGHT', 'share': 0.5})
            with self.assertRaisesRegex(CrsError, 'no active spatial unit'):
                create_rrr(db, {'baunit_id': baunit['id'], 'party_id': party['id'],
                    'site_id': self.site['id'], 'local_code': 'NOPE', 'rrr_type': 'RIGHT', 'share': 0.5})
            with self.assertRaisesRegex(CrsError, 'rrr_type'):
                create_rrr(db, {'baunit_id': baunit['id'], 'party_id': party['id'],
                    'site_id': self.site['id'], 'local_code': 'U1', 'rrr_type': 'OWNERSHIP'})
            count = db.execute(text('SELECT count(*) FROM rrr')).scalar_one()
            self.assertEqual(count, 0)

    def test_site_scoping_prevents_ambiguous_and_cross_site_rrr(self):
        other = self.make_site('98ZY76XW54VU32')
        process_properties(UUID(self.upload(site=other)['id']))
        with self.session() as db:
            party = create_party(db, {'party_type': 'person', 'name': 'Allottee'})
            baunit = create_baunit(db, {'name': 'Scheme A'})
            with self.assertRaises(AmbiguousUnit):
                create_rrr(db, {'baunit_id': baunit['id'], 'party_id': party['id'],
                    'local_code': 'U1', 'rrr_type': 'RIGHT', 'share': 0.4})
            first = create_rrr(db, {'baunit_id': baunit['id'], 'party_id': party['id'],
                'site_id': self.site['id'], 'local_code': 'U1', 'rrr_type': 'RIGHT', 'share': 0.4})
            second = create_rrr(db, {'baunit_id': baunit['id'], 'party_id': party['id'],
                'site_id': other['id'], 'local_code': 'U1', 'rrr_type': 'RIGHT', 'share': 0.4})
            self.assertNotEqual(first['spatial_unit_id'], second['spatial_unit_id'])
            db.commit()
        with self.session() as db:
            self.assertEqual(len(fetch_record(db, 'U1', self.site['id'])['rrr']), 1)
            self.assertEqual(len(fetch_record(db, 'U1', other['id'])['rrr']), 1)

    def test_right_share_totals_capped_but_restriction_is_not(self):
        with self.session() as db:
            party_a = create_party(db, {'party_type': 'person', 'name': 'A'})
            party_b = create_party(db, {'party_type': 'person', 'name': 'B'})
            water = create_party(db, {'party_type': 'organisation', 'name': 'Water dept'})
            baunit = create_baunit(db, {'name': 'Scheme A'})
            create_rrr(db, {'baunit_id': baunit['id'], 'party_id': party_a['id'],
                'site_id': self.site['id'], 'local_code': 'U1', 'rrr_type': 'RIGHT', 'share': 0.6})
            with self.assertRaises(ImportConflict):
                create_rrr(db, {'baunit_id': baunit['id'], 'party_id': party_b['id'],
                    'site_id': self.site['id'], 'local_code': 'U1', 'rrr_type': 'RIGHT', 'share': 0.5})
            # exact boundary (0.6 + 0.4 == 1) is allowed
            create_rrr(db, {'baunit_id': baunit['id'], 'party_id': party_b['id'],
                'site_id': self.site['id'], 'local_code': 'U1', 'rrr_type': 'RIGHT', 'share': 0.4})
            # restrictions on the same unit are not share-limited
            create_rrr(db, {'baunit_id': baunit['id'], 'party_id': water['id'],
                'site_id': self.site['id'], 'local_code': 'U1', 'rrr_type': 'RESTRICTION', 'share': 0.9})
            create_rrr(db, {'baunit_id': baunit['id'], 'party_id': water['id'],
                'site_id': self.site['id'], 'local_code': 'U1', 'rrr_type': 'RESPONSIBILITY', 'share': 0.9})
            db.commit()
        with self.session() as db:
            rows = list_rrr(db, self.site['id'])
            rights = [r for r in rows if r['rrr_type'] == 'RIGHT']
            self.assertEqual(round(sum(r['share'] for r in rights), 4), 1.0)

    def test_right_share_out_of_range_rejected(self):
        with self.session() as db:
            party = create_party(db, {'party_type': 'person', 'name': 'A'})
            baunit = create_baunit(db, {'name': 'Scheme A'})
            for bad in (0, -0.1, 1.5):
                with self.assertRaises(CrsError):
                    create_rrr(db, {'baunit_id': baunit['id'], 'party_id': party['id'],
                        'site_id': self.site['id'], 'local_code': 'U1', 'rrr_type': 'RIGHT', 'share': bad})

    def test_duplicate_rrr_combination_conflicts(self):
        with self.session() as db:
            party = create_party(db, {'party_type': 'person', 'name': 'A'})
            baunit = create_baunit(db, {'name': 'Scheme A'})
            create_rrr(db, {'baunit_id': baunit['id'], 'party_id': party['id'],
                'site_id': self.site['id'], 'local_code': 'U1', 'rrr_type': 'RIGHT', 'share': 0.3})
            with self.assertRaises(ImportConflict):
                create_rrr(db, {'baunit_id': baunit['id'], 'party_id': party['id'],
                    'site_id': self.site['id'], 'local_code': 'U1', 'rrr_type': 'RIGHT', 'share': 0.3})

    def test_baunit_link_and_consistency_conflict(self):
        with self.session() as db:
            baunit_a = create_baunit(db, {'name': 'Scheme A'})
            baunit_b = create_baunit(db, {'name': 'Scheme B'})
            link_baunit(db, baunit_a['id'], {'site_id': self.site['id'], 'local_code': 'U1'})
            # relinking the same baunit is a harmless no-op
            link_baunit(db, baunit_a['id'], {'site_id': self.site['id'], 'local_code': 'U1'})
            with self.assertRaises(ImportConflict):
                link_baunit(db, baunit_b['id'], {'site_id': self.site['id'], 'local_code': 'U1'})
            party = create_party(db, {'party_type': 'person', 'name': 'A'})
            with self.assertRaises(ImportConflict):
                create_rrr(db, {'baunit_id': baunit_b['id'], 'party_id': party['id'],
                    'site_id': self.site['id'], 'local_code': 'U1', 'rrr_type': 'RIGHT', 'share': 0.2})
            db.commit()
        with self.session() as db:
            rec = fetch_record(db, 'U1', self.site['id'])
            self.assertEqual(rec.get('rrr'), [])

    def test_baunit_uid_conflict(self):
        with self.session() as db:
            create_baunit(db, {'name': 'Scheme A', 'uid': 'BA-DUP'})
            with self.assertRaises(ImportConflict):
                create_baunit(db, {'name': 'Scheme A again', 'uid': 'BA-DUP'})

    def test_rights_establish_link_and_conflicting_link_cannot_replace_it(self):
        with self.session() as db:
            party=create_party(db,{'party_type':'person','name':'A'})
            a=create_baunit(db,{'name':'A'}); b=create_baunit(db,{'name':'B'})
            target={'local_code':'U1','site_id':self.site['id']}
            create_rrr(db,{**target,'party_id':party['id'],'baunit_id':a['id'],'rrr_type':'RIGHT','share':.5})
            with self.assertRaises(ImportConflict):
                link_baunit(db,b['id'],target)
            self.assertEqual(str(fetch_record(db,'U1',self.site['id'])['baunit_id']),a['id'])

    def test_uuid_cannot_override_site_or_code_and_old_links_are_immutable(self):
        other=self.make_site('98ZY76XW54VU32')
        target=self.unit_uuid('U1')
        with self.session() as db:
            ba=create_baunit(db,{'name':'A'})
            for extra in ({'site_id':other['id']},{'local_code':'WRONG'},{'site_id':'bad'}):
                with self.assertRaises(CrsError):
                    link_baunit(db,ba['id'],{'spatial_unit_id':target,**extra})
            db.execute(text("UPDATE spatial_unit SET status='EXTINGUISHED' WHERE id=:id"),{'id':target})
            with self.assertRaises(CrsError):
                link_baunit(db,ba['id'],{'spatial_unit_id':target})

    def test_operator_verified_claim_still_is_not_a_legal_title(self):
        with self.session() as db:
            party=create_party(db,{'party_type':'person','name':'A'})
            ba=create_baunit(db,{'name':'A'})
            payload={'local_code':'U1','site_id':self.site['id'],'party_id':party['id'],
                     'baunit_id':ba['id'],'rrr_type':'RIGHT','share':.5,'claim_status':'VERIFIED'}
            with self.assertRaises(CrsError):
                create_rrr(db,payload)
            rec=create_rrr(db,{**payload,'evidence_ref':'doc://claim'})
            self.assertTrue(rec['not_legal_title'])


if __name__ == '__main__':
    unittest.main()
