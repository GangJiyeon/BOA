import asyncio
import unittest
import httpx
import test_cosmetic_recommendation as f
from test_moisture_score60 import actual
from app.main import app
from app.services.moisture_scale60 import score_from_response, PROVISIONAL_GAINS, VERSION

class ProvisionalTests(unittest.TestCase):
    setUp=f.ApiDatabaseTests.setUp
    tearDown=f.ApiDatabaseTests.tearDown
    def test_gain_bounds_and_legacy(self):
        self.assertEqual(score_from_response(1.330049261),3)
        for version,gain in PROVISIONAL_GAINS.items():
            self.assertEqual(score_from_response(1.330049261,version),{5:7,10:11,20:28}[gain])
            self.assertEqual(score_from_response(0,version),0)
            self.assertEqual(score_from_response(100,version),60)
            for r in [13,23,28,40,46]:
                self.assertEqual(score_from_response(r/gain,version),score_from_response(r,VERSION))
    def test_save_reload_recommend_and_preserve_version(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                aid=(await c.post('/api/skin/analyses',json={'moisture_source':'none'})).json()['id']
                receipts=[]
                for version in [VERSION,*PROVISIONAL_GAINS]:
                    measured=actual(True);measured['normalization_version']=version
                    body={'analysis_id':aid,'result':measured}
                    response=await c.post('/api/skin/moisture/results',json=body)
                    self.assertEqual(response.status_code,200,response.text)
                    receipt=response.json();receipts.append((body,receipt))
                    self.assertEqual('임시 보정' in receipt['moisture_level_label'], version in PROVISIONAL_GAINS)
                    analysis=(await c.get(f'/api/skin/analyses/{aid}')).json()
                    response=await c.post('/api/cosmetics/recommendations/preview',json=dict(scores=analysis['scores'],score_semantics='photo_v1',moisture_analysis_id=aid,moisture_measurement_id=measured['measurement_id']))
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['hydration_policy']['normalized_score'],receipt['normalized_score'])
                for body,receipt in receipts:
                    self.assertEqual((await c.post('/api/skin/moisture/results',json=body)).json(),receipt)
        asyncio.run(flow())
