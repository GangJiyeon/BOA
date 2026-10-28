import asyncio
import unittest
from unittest.mock import patch
import copy

import httpx
import test_cosmetic_recommendation as f
from app.main import app
from app.schemas.moisture import CompletedMoisture
from app.services.hydration_estimate import estimate, VERSION, DISPLAY_VERSION
from test_moisture_fixed import actual


class EstimatorTests(unittest.TestCase):
    def test_actual_before_after_wash_values_keep_state_and_expand_display_only(self):
        # Actual representative counts from audit(3), not clinical truth labels.
        for count,shown in ((2506,24),(2502,27)):
            old=estimate(2538,count,44)
            new=estimate(2538,count,44,DISPLAY_VERSION)
            self.assertEqual(old['normalized_score'],3)
            self.assertEqual(new['normalized_score'],shown)
            for key in ('estimated_state','manufacturer_response','estimation_version','validation_level'):
                self.assertEqual(old[key],new[key])
            self.assertEqual(new['normalization_version'],DISPLAY_VERSION)

    def test_published_integer_bands_and_matching_display_categories(self):
        # Six published labels collapsed to low / normal / sufficient.
        cases = [(0.5,'low'),(12,'low'),(22,'low'),(22.999,'low'),
                 (23,'normal'),(27,'normal'),(39,'normal'),(45.999,'normal'),
                 (46,'sufficient'),(65,'sufficient'),(99,'sufficient')]
        for response, state in cases:
            scores=[]
            for divider in (11,22,44):
                baseline=(500+170)*divider/11-170
                count=(500*(1-response/100)+170)*divider/11-170
                result=estimate(baseline,count,divider)
                with self.subTest(response=response,divider=divider):
                    self.assertEqual(result['estimated_state'],state)
                    self.assertEqual(result['validation_level'],'experimental_unvalidated')
                    lo,hi={'low':(1,33),'normal':(34,66),'sufficient':(67,100)}[state]
                    self.assertTrue(lo<=result['normalized_score']<=hi)
                scores.append(result['normalized_score'])
            self.assertEqual(len(set(scores)),1,'equivalent signals must survive divider conversion')

    def test_missing_unverified_or_unsupported_profiles_are_not_guessed(self):
        for change in ('missing','divider','gain','offset','fin','verified'):
            body=actual(True)
            if change=='missing':body.pop('sensor_profile')
            else:
                key,value={'divider':('reference_divider',10),'gain':('output_gain',4),
                    'offset':('offset',0),'fin':('sensor_divider',1),'verified':('verified',False)}[change]
                body['sensor_profile'][key]=value
            with self.subTest(change=change),self.assertRaises(ValueError):
                CompletedMoisture.model_validate(body)

    def test_a_capacitance_response_alone_is_not_the_new_model(self):
        body=actual(True)
        body['normalization_version']='boa-cap-response-10-v1'
        legacy=CompletedMoisture.model_validate(body)
        from app.services.moisture_normalization import normalize
        self.assertNotIn('estimated_state',normalize(legacy))
        with self.assertRaises(ValueError):estimate(2540,500,44)
        with self.assertRaises(ValueError):estimate(2540,2540,44)


class EstimatorFlowTests(unittest.TestCase):
    setUp=f.ApiDatabaseTests.setUp
    tearDown=f.ApiDatabaseTests.tearDown

    def test_display_v2_persists_and_does_not_change_products_or_policy(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                aid=(await client.post('/api/skin/analyses',json={'moisture_source':'none'})).json()['id']
                request=None;previous=None
                for i,version in enumerate((VERSION,DISPLAY_VERSION)):
                    result=actual(True);result['normalization_version']=version
                    result['measurement_id']=f'00000000-0000-4000-8000-{i+100:012d}'
                    result['sensor_profile']['drive_current_code']=18
                    saved=await client.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':result})
                    self.assertEqual(saved.status_code,200,saved.text)
                    fetched=(await client.get(f'/api/skin/analyses/{aid}')).json()
                    request=dict(scores=fetched['scores'],score_semantics='photo_v1',moisture_analysis_id=aid,
                        moisture_measurement_id=result['measurement_id'],avoid_dryness_triggers=True)
                    response=await client.post('/api/cosmetics/recommendations/preview',json=request)
                    self.assertEqual(response.status_code,200,response.text)
                    current=response.json()
                    if previous:
                        self.assertNotEqual(saved.json()['normalized_score'],3)
                        self.assertEqual(previous['hydration_policy'],current['hydration_policy'])
                        self.assertEqual(previous['recommendations'],current['recommendations'])
                    previous=current
        asyncio.run(flow())

    def test_display_changes_cannot_change_sensor_policy_or_products(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                aid=(await client.post('/api/skin/analyses',json={'moisture_source':'none'})).json()['id']
                measured=actual(True)
                saved=await client.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':measured})
                self.assertEqual(saved.status_code,200,saved.text)
                fetched=(await client.get(f'/api/skin/analyses/{aid}')).json()
                request=dict(scores=fetched['scores'],score_semantics='photo_v1',moisture_analysis_id=aid,
                    moisture_measurement_id=measured['measurement_id'],avoid_dryness_triggers=True)
                responses=[]
                for score,category in ((1,'개선 필요'),(50,'보통'),(100,'양호')):
                    body=copy.deepcopy(request)
                    for item in body['scores']:
                        if item['metric_code']=='moisture':item.update(score=score,category_name=category)
                    response=await client.post('/api/cosmetics/recommendations/preview',json=body)
                    self.assertEqual(response.status_code,200,response.text)
                    responses.append(response.json())
                self.assertEqual(responses[0],responses[1]);self.assertEqual(responses[0],responses[2])
                self.assertEqual(responses[0]['hydration_policy']['basis'],'persisted_sensor_estimate')
                original=responses[0]
                # Even a server-side display change across the old DB bands
                # cannot change the classification or chosen products.
                with patch('app.services.hydration_estimate.display_score',return_value=90):
                    changed=await client.post('/api/cosmetics/recommendations/preview',json=request)
                    presentation=await client.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':actual(True)})
                    self.assertEqual(presentation.status_code,200,presentation.text)
                    self.assertEqual(presentation.json()['normalized_score'],90)
                    self.assertEqual(presentation.json()['score_category'],'개선 필요')
                self.assertEqual(changed.status_code,200,changed.text)
                self.assertEqual(changed.json()['hydration_policy'],original['hydration_policy'])
                self.assertEqual(changed.json()['recommendations'],original['recommendations'])
                bad=copy.deepcopy(request);bad['moisture_analysis_id']=aid+1
                self.assertEqual((await client.post('/api/cosmetics/recommendations/preview',json=bad)).status_code,422)
        asyncio.run(flow())

    def test_excluded_warning_samples_never_enter_the_measurement_value(self):
        measured=actual(True)
        removed=measured['samples'].pop(10)
        measured['discarded_samples']=[dict(sequence=removed['sequence'],uptime_ms=removed['uptime_ms'],
            status='sensor_error',warning_flags=0x1000,diagnostic_count=100)]
        checked=CompletedMoisture.model_validate(measured)
        from app.services.moisture_normalization import normalize
        self.assertEqual(normalize(checked)['terminal_count'],2506)
        self.assertEqual(checked.statistics()['warning_sample_count'],1)
        self.assertEqual(checked.statistics()['sample_count'],29)
        duplicate=copy.deepcopy(measured);duplicate['discarded_samples'][0]['sequence']=measured['samples'][0]['sequence']
        with self.assertRaises(ValueError):CompletedMoisture.model_validate(duplicate)
        terminal=copy.deepcopy(measured)
        terminal['discarded_samples'][0]['sequence']=terminal['samples'][-1]['sequence']
        terminal['discarded_samples'][0]['uptime_ms']=terminal['samples'][-1]['uptime_ms']
        terminal['samples'].pop()
        with self.assertRaises(ValueError):CompletedMoisture.model_validate(terminal)

    def test_each_sensor_state_reaches_stored_analysis_and_recommendation(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                for count,state,category in ((2506,'low','개선 필요'),(1951,'normal','보통'),(1200,'sufficient','양호')):
                    aid=(await client.post('/api/skin/analyses',json={'moisture_source':'none'})).json()['id']
                    result=actual(True)
                    for sample in result['samples']:sample['count']=count
                    saved=await client.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':result})
                    self.assertEqual(saved.status_code,200,saved.text)
                    receipt=saved.json()
                    self.assertEqual(receipt['estimated_state'],state)
                    self.assertEqual(receipt['score_category'],category)
                    self.assertTrue(receipt['used_for_scoring'])
                    fetched=(await client.get(f'/api/skin/analyses/{aid}')).json()
                    self.assertEqual(fetched['moisture_measurement']['estimation_version'],VERSION)
                    self.assertEqual(fetched['scores'][0]['category_name'],category)
                    preview=await client.post('/api/cosmetics/recommendations/preview',json={
                        'scores':fetched['scores'],'score_semantics':'photo_v1','avoid_dryness_triggers':True})
                    self.assertEqual(preview.status_code,200,preview.text)
                    self.assertEqual(preview.json()['hydration_policy']['state'],state)
                    self.assertEqual(preview.json()['hydration_policy']['dryness_exclusion_enabled'],state=='low')
        asyncio.run(flow())

    def test_old_arbitrary_scale_cannot_create_a_new_hydration_classification(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                aid=(await client.post('/api/skin/analyses',json={'moisture_source':'none'})).json()['id']
                saved=await client.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':actual()})
                self.assertEqual(saved.status_code,200,saved.text)
                self.assertFalse(saved.json()['used_for_scoring'])
                fetched=(await client.get(f'/api/skin/analyses/{aid}')).json()
                self.assertFalse(any(s['metric_code']=='moisture' for s in fetched['scores']))
        asyncio.run(flow())
