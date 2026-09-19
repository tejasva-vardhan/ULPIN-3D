"""Survey declarations remain tied to control-point source bytes and site."""

import os
from pathlib import Path
import unittest
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.geo import CrsError
from app.ingest import ImportConflict, create_site, ingest_dataset
from app.survey import SurveyDeclaration, get_survey, record_survey


def control_point(coordinates=(500005, 2050005)):
    return {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'station': 'GCP-1'},
         'geometry': {'type': 'Point', 'coordinates': coordinates}}]}


class SurveyInputTests(unittest.TestCase):
    def test_accuracy_and_evidence_are_required(self):
        for accuracy in (0, -1, float('nan'), float('inf')):
            with self.subTest(accuracy=accuracy), self.assertRaises(ValidationError):
                SurveyDeclaration(method='CORS', h_rmse_m=accuracy, evidence_ref='report-1')
        with self.assertRaises(ValidationError):
            SurveyDeclaration(method='unknown', h_rmse_m=0.02, evidence_ref='report-1')
        with self.assertRaises(ValidationError):
            SurveyDeclaration(method='GNSS', h_rmse_m=0.02)


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'set TEST_DATABASE_URL to a disposable PostGIS database')
class SurveyDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(os.environ['TEST_DATABASE_URL'])
        self.conn = self.engine.connect()
        self.transaction = self.conn.begin()
        self.db = Session(bind=self.conn, join_transaction_mode='create_savepoint')
        self.site = create_site(self.db, {'name': 'Survey test', 'epsg': 32643,
                                          'parent_ulpin': '12AB34CD56EF78'})
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.transaction.rollback()
        self.conn.close()
        self.engine.dispose()

    def source(self, raw=None):
        row = ingest_dataset(self.db, {'site_id': self.site['id'], 'kind': 'survey-control',
            'epsg': 32643, 'filename': 'control.geojson',
            'geojson': raw or control_point(), 'geom_origin': 'SURVEY'}, Path('.'))
        self.db.commit()
        return UUID(row['id'])

    def test_control_points_keep_provenance_and_declaration_is_immutable(self):
        source_id = self.source()
        declaration = SurveyDeclaration(method='CORS', h_rmse_m=0.03,
                                        v_rmse_m=0.05, evidence_ref='field-log-1')
        first = record_survey(self.db, source_id, declaration)
        self.assertFalse(first['reused'])
        self.assertEqual(first['point_count'], 1)
        self.assertEqual(len(first['source_checksum_sha256']), 64)
        self.assertEqual(first['source_epsg'], 32643)
        self.assertEqual(get_survey(self.db, source_id)['method'], 'CORS')
        self.assertTrue(record_survey(self.db, source_id, declaration)['reused'])
        with self.assertRaises(ImportConflict):
            record_survey(self.db, source_id, SurveyDeclaration(
                method='CORS', h_rmse_m=0.06, evidence_ref='field-log-1'))

    def test_rejects_3d_or_nonpoint_control_geometry(self):
        source_id = self.source(control_point((500005, 2050005, 10)))
        with self.assertRaisesRegex(CrsError, '2D Point'):
            record_survey(self.db, source_id, SurveyDeclaration(
                method='GNSS', h_rmse_m=0.1, evidence_ref='log'))


if __name__ == '__main__':
    unittest.main()
