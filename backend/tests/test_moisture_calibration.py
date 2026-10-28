import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx
import test_cosmetic_recommendation as fixture
from test_moisture_results import result
from app.main import app
from app.schemas.moisture import CompletedMoisture
from app.services.cheek_calibration import CheekProfile, convert

# Synthetic test fixture only. Never deployed as a real skin calibration.
def profile():
    return dict(version='TEST-ONLY',status='reviewed',site='left_cheek',algorithm_version='cheek-auto-v1',
                reference_device='synthetic',reference_unit='test_unit',evidence='synthetic unit-test fixture',
                score_basis='synthetic scores, not skin calibration',baseline_min=490,baseline_max=510,
                response_to_reference=[dict(x=0,y=0),dict(x=100,y=100)],
                reference_to_score=[dict(x=0,y=0),dict(x=100,y=100)])

class CalibrationTests(unittest.TestCase):
    def test_bounds_review_and_invalid_profiles(self):
        p=CompletedMoisture.model_validate(result())
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/'profile.json';file.write_text(json.dumps(profile()))
            with patch('app.services.cheek_calibration.get_settings',return_value=SimpleNamespace(moisture_calibration_profile=str(file))):
                self.assertEqual(convert(p,3.61)['calibrated_score'],4)
                self.assertEqual(convert(p,-1)['scoring_status'],'outside_calibration_range')
                p.baseline=700;self.assertEqual(convert(p,20)['scoring_status'],'outside_calibration_range');p.baseline=500
                data=profile();data['status']='draft';file.write_text(json.dumps(data));self.assertEqual(convert(p,20)['scoring_status'],'calibration_unreviewed')
                file.write_text('{}');self.assertEqual(convert(p,20)['scoring_status'],'calibration_invalid')
            data=profile();data['response_to_reference'][1]['x']=0
            with self.assertRaises(ValueError):CheekProfile.model_validate(data)

class CalibratedFlowTests(unittest.TestCase):
    setUp=fixture.ApiDatabaseTests.setUp
    tearDown=fixture.ApiDatabaseTests.tearDown
    def test_measurement_changes_analysis_and_recommendation(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                created=(await c.post('/api/skin/analyses',json={'moisture_source':'none'})).json();aid=created['id']
                before=await c.post('/api/cosmetics/recommendations/preview',json={'scores':created['scores']})
                self.assertEqual(before.status_code,200,before.text)
                self.assertIn('moisture',before.json()['missing_metrics'])
                payload=result();saved=await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':payload})
                self.assertEqual(saved.status_code,200,saved.text);self.assertTrue(saved.json()['used_for_scoring'])
                analysis=(await c.get(f'/api/skin/analyses/{aid}')).json()
                self.assertEqual(analysis['moisture_source'],'sensor')
                self.assertEqual(next(s['score'] for s in analysis['scores'] if s['metric_code']=='moisture'),20)
                after=await c.post('/api/cosmetics/recommendations/preview',json={'scores':analysis['scores']})
                self.assertEqual(after.status_code,200,after.text)
                a=next(a for a in after.json()['assessments'] if a['code']=='moisture')
                self.assertTrue(a['needs_improvement']);self.assertNotIn('moisture',after.json()['missing_metrics'])
                self.assertTrue(any(m['metric_code']=='moisture' for p in after.json()['recommendations'] for m in p['matches']),after.text)
                # File changes must not silently reinterpret an old saved observation.
                self.profile_file.write_text('{}')
                repeat=await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':payload})
                self.assertEqual(saved.json(),repeat.json())
        with tempfile.TemporaryDirectory() as td:
            self.profile_file=Path(td)/'profile.json';self.profile_file.write_text(json.dumps(profile()))
            with patch('app.services.cheek_calibration.get_settings',return_value=SimpleNamespace(moisture_calibration_profile=str(self.profile_file))):
                asyncio.run(flow())
