import asyncio, copy, unittest, json
from pathlib import Path
from uuid import uuid4
import httpx
import test_cosmetic_recommendation as f
from app.main import app
from app.schemas.moisture import CompletedMoisture
from app.services.cheek_signal import signal_statistics


def measurement():
    return dict(measurement_id=str(uuid4()), algorithm_version='skin-auto-v3', site='skin',
        measured_at='2026-10-28T01:00:00Z', baseline=500,contact_threshold=0.4,release_threshold=0.2,
        air_samples=[dict(sequence=i,uptime_ms=100+i*100,count=500) for i in range(21)],
        samples=[dict(sequence=40+i,uptime_ms=4000+i*100,count=497) for i in range(31)])

class ContactTests(unittest.TestCase):
    def test_latest_descent_requires_stationary_window(self):
        r=json.loads((Path(__file__).parents[2]/'fixtures/skin-window-fine.json').read_text())
        CompletedMoisture.model_validate(r) # Preserve the old v5 contract.
        r['algorithm_version']='skin-auto-v6'
        with self.assertRaisesRegex(ValueError,'signal drift'):
            CompletedMoisture.model_validate(r)
        old=signal_statistics(r['baseline'],[s['count'] for s in r['samples']],modern=True,guarded=True)
        new=signal_statistics(r['baseline'],[s['count'] for s in r['samples']],modern=True,guarded=True,stationary=True)
        self.assertAlmostEqual(old['experimental_index'],new['experimental_index'])
        self.assertGreater(new['capacitance_drift_pp'],new['drift_limit_pp'])
        for i,s in enumerate(r['samples']):s['count']=2495+i%2
        CompletedMoisture.model_validate(r) # Stable one-code jitter is allowed.
    def test_finer_acquisition_same_response(self):
        # Synthetic equivalent input, not evidence of skin hydration accuracy.
        r=measurement();r.update(algorithm_version='skin-auto-v5',baseline=2542,
            contact_threshold=200/2542,release_threshold=100/2542)
        for s in r['air_samples']:s['count']=2542
        for s in r['samples']:s['count']=2526
        CompletedMoisture.model_validate(r)
        old=signal_statistics(508,[504]*31,modern=True,guarded=True)
        new=signal_statistics(2542,[2526]*31,modern=True,guarded=True)
        self.assertAlmostEqual(old['experimental_index'],new['experimental_index'])
        self.assertLess(new['response_step_pp'],old['response_step_pp']/3.99)
        self.assertFalse(new['resolution_limited'])
    def test_gentle_contact_and_air_evidence(self):
        CompletedMoisture.model_validate(measurement())
        r=measurement();r.pop('air_samples')
        with self.assertRaises(ValueError):CompletedMoisture.model_validate(r)
        r=measurement();r['contact_threshold']=.1;r['release_threshold']=.05
        with self.assertRaises(ValueError):CompletedMoisture.model_validate(r)
        r=measurement();r['air_samples'][3]['count']=495
        with self.assertRaises(ValueError):CompletedMoisture.model_validate(r)
        r=measurement()
        for sample in r['samples']:sample['count']=0
        with self.assertRaises(ValueError):CompletedMoisture.model_validate(r)
    def test_physical_fraction_and_robustness(self):
        expected=100*(1-(667/670)**2)
        a=signal_statistics(500,[497]*31,modern=True)
        self.assertAlmostEqual(a['experimental_index'],expected)
        self.assertEqual(a['signal_policy'],'skin-contact-fraction-v1')
        self.assertEqual(a['experimental_index'],signal_statistics(500,[497]*30+[496],modern=True)['experimental_index'])
        self.assertEqual(signal_statistics(500,[500]*31,modern=True)['experimental_index'],0)

class ContactApiTests(unittest.TestCase):
    setUp=f.ApiDatabaseTests.setUp
    tearDown=f.ApiDatabaseTests.tearDown
    def test_real_value_saved_and_recomputed_for_recommendation(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                a=(await c.post('/api/skin/analyses',json={'moisture_source':'none'})).json()
                r=measurement();body={'analysis_id':a['id'],'result':r}
                saved=await c.post('/api/skin/moisture/results',json=body)
                self.assertEqual(saved.status_code,200,saved.text)
                value=saved.json();self.assertEqual(value['site'],'skin')
                self.assertEqual(value['unit'],'capacitance_contact_fraction_percent')
                self.assertFalse(value['used_for_scoring']);self.assertTrue(value['recommendation_eligible'])
                retry=await c.post('/api/skin/moisture/results',json=body)
                self.assertEqual(value,retry.json())
                response=await c.post('/api/cosmetics/recommendations/preview',json=dict(scores=a['scores'],moisture_analysis_id=a['id'],moisture_measurement_id=r['measurement_id']))
                self.assertEqual(response.status_code,200,response.text)
                auxiliary=response.json()['sensor_auxiliary']
                self.assertTrue(auxiliary['applied']);self.assertAlmostEqual(auxiliary['experimental_index'],value['experimental_index'])
                self.assertEqual(auxiliary['policy'],'skin-contact-fraction-tie-v1')
                self.assertTrue(any(p['sensor_auxiliary_bonus']>0 for p in response.json()['recommendations']))
                fetched=(await c.get(f"/api/skin/analyses/{a['id']}")).json()
                self.assertEqual(fetched['moisture_measurement']['experimental_index'],value['experimental_index'])
        asyncio.run(flow())


class GuardTests(unittest.TestCase):
    def test_actual_window_new_version_waits_but_legacy_is_preserved(self):
        r=measurement();r['baseline']=507;r['contact_threshold']=200/507;r['release_threshold']=100/507
        for a in r['air_samples']:a['count']=507
        for i,x in enumerate(r['samples']):x['count']=504 if i==0 else 503 if i<25 else 502
        CompletedMoisture.model_validate(r) # Do not reinterpret an existing v3 result.
        r['algorithm_version']='skin-auto-v4'
        with self.assertRaises(ValueError):CompletedMoisture.model_validate(r)
        for x in r['samples']:x['count']=503
        CompletedMoisture.model_validate(r)
        q=signal_statistics(507,[503]*31,modern=True,guarded=True)
        self.assertTrue(q['resolution_limited'])
        self.assertLess(q['response_lower'],q['experimental_index']);self.assertGreater(q['response_upper'],q['experimental_index'])

class GuardApiTests(unittest.TestCase):
    setUp=f.ApiDatabaseTests.setUp
    tearDown=f.ApiDatabaseTests.tearDown
    def test_weak_response_saved_but_not_used_to_rank_products(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                analysis=(await c.post('/api/skin/analyses',json={'moisture_source':'none'})).json();aid=analysis['id']
                r=measurement();r['algorithm_version']='skin-auto-v4'
                saved=await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':r})
                self.assertEqual(saved.status_code,200,saved.text)
                q=saved.json();self.assertTrue(q['resolution_limited']);self.assertFalse(q['recommendation_eligible'])
                self.assertEqual(q['scoring_status'],'resolution_limited')
                resp=await c.post('/api/cosmetics/recommendations/preview',json=dict(scores=analysis['scores'],moisture_analysis_id=aid,moisture_measurement_id=r['measurement_id']))
                self.assertEqual(resp.status_code,422)
                r['measurement_id']=str(uuid4())
                for x in r['samples']:x['count']=488
                saved=await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':r})
                self.assertEqual(saved.status_code,200,saved.text);self.assertTrue(saved.json()['recommendation_eligible'])
                self.assertFalse(saved.json()['resolution_limited'])
                resp=await c.post('/api/cosmetics/recommendations/preview',json=dict(scores=analysis['scores'],moisture_analysis_id=aid,moisture_measurement_id=r['measurement_id']))
                self.assertEqual(resp.status_code,200,resp.text)
                self.assertAlmostEqual(resp.json()['sensor_auxiliary']['experimental_index'],saved.json()['experimental_index'])
        asyncio.run(flow())


class ConfirmedOnlyTests(unittest.TestCase):
    setUp=f.ApiDatabaseTests.setUp
    tearDown=f.ApiDatabaseTests.tearDown
    def test_v6_descent_not_saved_but_single_plateau_reaches_recommendation(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                analysis=(await c.post('/api/skin/analyses',json={'moisture_source':'none'})).json();aid=analysis['id']
                r=json.loads((Path(__file__).parents[2]/'fixtures/skin-window-fine.json').read_text())
                r.update(measurement_id=str(uuid4()),algorithm_version='skin-auto-v6')
                saved=await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':r})
                self.assertEqual(saved.status_code,422,saved.text)
                fetched=(await c.get(f'/api/skin/analyses/{aid}')).json()
                self.assertIsNone(fetched['moisture_measurement'])
                for s in r['samples']:s['count']=2495
                saved=await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':r})
                self.assertEqual(saved.status_code,200,saved.text)
                self.assertEqual(saved.json()['algorithm_version'],'skin-auto-v6')
                self.assertTrue(saved.json()['recommendation_eligible'])
                again=await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':r})
                self.assertEqual(again.json(),saved.json())
                rec=await c.post('/api/cosmetics/recommendations/preview',json=dict(scores=analysis['scores'],moisture_analysis_id=aid,moisture_measurement_id=r['measurement_id']))
                self.assertEqual(rec.status_code,200,rec.text)
                self.assertTrue(rec.json()['sensor_auxiliary']['applied'])
                self.assertAlmostEqual(rec.json()['sensor_auxiliary']['experimental_index'],saved.json()['experimental_index'])
        asyncio.run(flow())
    def test_v5_rejects_weak_upload_without_persisting(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                analysis=(await c.post('/api/skin/analyses',json={'moisture_source':'none'})).json();aid=analysis['id']
                r=measurement();r['algorithm_version']='skin-auto-v5'
                resp=await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':r})
                self.assertEqual(resp.status_code,422,resp.text)
                fetched=(await c.get(f'/api/skin/analyses/{aid}')).json()
                self.assertIsNone(fetched['moisture_measurement'])
                r['measurement_id']=str(uuid4())
                for x in r['samples']:x['count']=488
                resp=await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':r})
                self.assertEqual(resp.status_code,200,resp.text)
                self.assertTrue(resp.json()['recommendation_eligible']);self.assertFalse(resp.json()['resolution_limited'])
                rec=await c.post('/api/cosmetics/recommendations/preview',json=dict(scores=analysis['scores'],moisture_analysis_id=aid,moisture_measurement_id=r['measurement_id']))
                self.assertEqual(rec.status_code,200,rec.text)
                self.assertTrue(rec.json()['sensor_auxiliary']['applied'])
        asyncio.run(flow())
