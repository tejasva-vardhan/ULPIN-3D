"""Accuracy-report contract; authored fixtures never count as real evidence."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from shapely.geometry import box, mapping

from app.evaluation import evaluate_case, evaluate_cases
from app.geo import CrsError
from elevation_fixtures import cloud_file, raster_file


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.parcel = box(500000, 2050000, 500030, 2050020)
        self.roof = box(500002, 2050002, 500022, 2050012)

    def tearDown(self):
        self.temp.cleanup()

    def manifest(self, elevation, *, kind='synthetic', reference=None, case_id='sample'):
        path = self.root / (case_id+'.json')
        path.write_text(json.dumps({
            'case_id':case_id, 'data_kind':kind,
            'parcel':{'epsg':32643,'geometry':mapping(self.parcel)},
            'reference':{'epsg':32643,'footprint':mapping(reference or self.roof),
                         'height_m':9,'height_definition':'roof above local ground',
                         'source':'authored fixture; not an independent real survey'},
            'elevation':elevation,
        }),encoding='utf-8')
        return path

    def test_classified_cloud_reports_errors_and_zero_real_cases(self):
        cloud_file(self.root/'cloud.las')
        path=self.manifest({'kind':'las','path':'cloud.las','z_ref':'ORTHOMETRIC_EGM','local_zero_m':430})
        report=evaluate_cases([path])
        self.assertEqual(report['summary']['real_case_count'],0)
        self.assertIsNone(report['summary']['real_only'])
        row=report['cases'][0]
        self.assertAlmostEqual(row['estimator']['height_m'],9,places=2)
        self.assertGreater(row['metrics']['footprint_iou'],0.85)
        self.assertEqual(len(row['inputs'][0]['sha256']),64)
        self.assertAlmostEqual(row['metrics']['height_absolute_error_m'],0,places=2)
        self.assertEqual(row['geometry_epsg'],32643)
        self.assertEqual(row['estimator']['footprint']['type'],'Polygon')

    def test_wrong_reference_height_and_shape_produce_nonzero_errors(self):
        cloud_file(self.root/'cloud.las')
        path=self.manifest({'kind':'las','path':'cloud.las','z_ref':'LOCAL_SITE','local_zero_m':0},
                           reference=box(500003,2050002,500023,2050012))
        case=json.loads(path.read_text(encoding='utf-8'))
        case['reference']['height_m']=12
        path.write_text(json.dumps(case),encoding='utf-8')
        row=evaluate_case(path)
        self.assertAlmostEqual(row['metrics']['height_error_m'],-3,places=2)
        self.assertGreater(row['metrics']['centroid_error_m'],0)
        self.assertLess(row['metrics']['footprint_iou'],1)

    def test_raster_pair_and_missing_reference_or_crs_fail_closed(self):
        raster_file(self.root/'dsm.tif',surface=True)
        raster_file(self.root/'dtm.tif',surface=False,resolution=2)
        path=self.manifest({'kind':'dsm_dtm','dsm':'dsm.tif','dtm':'dtm.tif',
                            'z_ref':'ORTHOMETRIC_EGM','local_zero_m':430})
        row=evaluate_case(path)
        self.assertAlmostEqual(row['estimator']['height_m'],9,places=2)
        data=json.loads(path.read_text(encoding='utf-8'))
        data['reference'].pop('source')
        path.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaises(CrsError): evaluate_case(path)
        data['reference']['source']='reference'
        data['parcel'].pop('epsg')
        path.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaises(CrsError): evaluate_case(path)

    def test_duplicate_case_ids_are_rejected(self):
        cloud_file(self.root/'cloud.las')
        a=self.manifest({'kind':'las','path':'cloud.las','z_ref':'LOCAL_SITE','local_zero_m':0})
        b=self.root/'copy.json'; b.write_bytes(a.read_bytes())
        with self.assertRaisesRegex(CrsError,'case_id'): evaluate_cases([a,b])

    def test_cli_writes_a_report_without_claiming_real_accuracy(self):
        cloud_file(self.root/'cloud.las')
        case = self.manifest({'kind':'las','path':'cloud.las',
                              'z_ref':'LOCAL_SITE','local_zero_m':0})
        report_path = self.root/'report.json'
        result = subprocess.run([sys.executable, '-m', 'app.evaluation',
                                 str(case), '--output', str(report_path)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(report_path.read_text(encoding='utf-8'))
        self.assertIsNone(report['summary']['real_only'])
        self.assertEqual(report['summary']['synthetic_case_count'], 1)

    def test_out_of_zone_parcel_is_rejected(self):
        cloud_file(self.root/'cloud.las')
        case = self.manifest({'kind':'las','path':'cloud.las',
                              'z_ref':'LOCAL_SITE','local_zero_m':0})
        data = json.loads(case.read_text(encoding='utf-8'))
        data['parcel'] = {'epsg':4326, 'geometry':mapping(box(0, 0, 0.001, 0.001))}
        case.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(CrsError, 'outside the EPSG:32643'):
            evaluate_case(case)


if __name__ == '__main__':
    unittest.main()
