import asyncio
import unittest
from uuid import uuid4
import httpx
import test_cosmetic_recommendation as f
from test_moisture_results import result
from app.main import app
from app.schemas.moisture import CompletedMoisture
from app.services.cheek_signal import capacitance_change, signal_statistics
from app.services.cosmetic_recommendation import recommend
from app.services.cosmetic_rule_types import load_seed_bundle


def measured(count=488):
    r=result();r['algorithm_version']='cheek-auto-v2'
    for s in r['samples']:s['count']=count
    return r


class SignalTests(unittest.TestCase):
    def test_offset_formula_and_span(self):
        self.assertAlmostEqual(capacitance_change(506,493.71),3.73771307455)
        self.assertEqual(capacitance_change(506,506),0)
        s=signal_statistics(506,[476]*31)
        self.assertAlmostEqual(s['experimental_index'],100)
        self.assertTrue(s['index_saturated'])

    def test_quality_gate(self):
        CompletedMoisture.model_validate(measured())
        r=measured()
        for i,s in enumerate(r['samples']):s['count']=488 if i%2 else 480
        with self.assertRaises(ValueError):CompletedMoisture.model_validate(r)
        r=measured()
        for i,s in enumerate(r['samples']):s['count']=490-i//6
        with self.assertRaises(ValueError):CompletedMoisture.model_validate(r)

    def test_only_existing_ties_change_and_exclusions_preserved(self):
        scores=dict(moisture=None,redness=80,brightness=20,trouble=80,uniformity=80)
        req=f.request(scores=scores,avoid_redness_triggers=False)
        products=[f.product(1,('나이아신아마이드',)),f.product(2,('나이아신아마이드','글리세린')),
                  f.product(3,('나이아신아마이드','살리실릭애씨드'))]
        args=dict(rule_bundle=load_seed_bundle())
        before=recommend(req,f.definitions(),products,f.KNOWN,**args)
        aux=dict(experimental_index=40,measurement_id=str(uuid4()),applied=True)
        after=recommend(req,f.definitions(),products,f.KNOWN,**args,sensor_auxiliary=aux)
        self.assertEqual([p.product_id for p in before.recommendations],[3,1,2])
        self.assertEqual([p.product_id for p in after.recommendations],[3,2,1])
        self.assertEqual(after.recommendations[1].match_count,1)
        excluded=f.request(scores=scores,excluded_ingredients=['글리세린'],avoid_redness_triggers=False)
        after=recommend(excluded,f.definitions(),products,f.KNOWN,**args,sensor_auxiliary=aux)
        self.assertNotIn(2,[p.product_id for p in after.recommendations])


class SignalApiTests(unittest.TestCase):
    setUp=f.ApiDatabaseTests.setUp
    tearDown=f.ApiDatabaseTests.tearDown
    def test_save_to_recommendation_with_no_fake_clinical_score(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                analysis=(await c.post('/api/skin/analyses',json={'moisture_source':'none'})).json()
                aid=analysis['id'];r=measured()
                saved=await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':r})
                self.assertEqual(saved.status_code,200,saved.text)
                self.assertTrue(saved.json()['recommendation_eligible'])
                self.assertFalse(saved.json()['used_for_scoring'])
                self.assertEqual(saved.json()['scoring_status'],'experimental_auxiliary')
                fetched=(await c.get(f'/api/skin/analyses/{aid}')).json()
                self.assertEqual(fetched['scores'],analysis['scores'])
                body=dict(scores=analysis['scores'],moisture_analysis_id=aid,moisture_measurement_id=r['measurement_id'])
                response=await c.post('/api/cosmetics/recommendations/preview',json=body)
                self.assertEqual(response.status_code,200,response.text)
                self.assertTrue(response.json()['sensor_auxiliary']['applied'])
                self.assertTrue(any(p['sensor_auxiliary_bonus']>0 for p in response.json()['recommendations']))
                self.assertFalse(any(a['code']=='moisture' for a in response.json()['assessments']))
                body['moisture_analysis_id']=aid+1
                self.assertEqual((await c.post('/api/cosmetics/recommendations/preview',json=body)).status_code,422)
                saturated=measured(400)
                saved=await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':saturated})
                self.assertFalse(saved.json()['recommendation_eligible'])
                body.update(moisture_analysis_id=aid,moisture_measurement_id=saturated['measurement_id'])
                self.assertEqual((await c.post('/api/cosmetics/recommendations/preview',json=body)).status_code,422)
        asyncio.run(flow())
