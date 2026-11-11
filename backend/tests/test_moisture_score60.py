"""Boundary, compatibility and persisted recommendation tests for the new scale."""
import asyncio
import copy
import math
import unittest

import httpx
import test_cosmetic_recommendation as f
from app.main import app
from app.services.moisture_scale60 import VERSION, LEGACY_VERSION, classification, score_from_response
from app.services.hydration_estimate import estimate, VERSION as OLD_VERSION, DISPLAY_VERSION
from test_moisture_fixed import actual


class Score60Tests(unittest.TestCase):
    def test_sqrt_changes_only_within_level_and_preserves_old_records(self):
        for i in range(100001):
            response=i/1000
            old=score_from_response(response,LEGACY_VERSION)
            new=score_from_response(response,VERSION)
            self.assertEqual(classification(old)['moisture_level'],classification(new)['moisture_level'])
            self.assertGreaterEqual(new,old)
        # Latest uploaded sample: exact source values, independently verified.
        old=estimate(2538,2488.5,44,LEGACY_VERSION)
        new=estimate(2538,2488.5,44,VERSION)
        self.assertAlmostEqual(new['manufacturer_response'],2.440828402366864)
        self.assertEqual((old['normalized_score'],new['normalized_score']),(1,4))
        self.assertEqual((old['moisture_level'],new['moisture_level']),(1,1))
        self.assertEqual(old['estimation_version'],LEGACY_VERSION)
        self.assertEqual(new['estimation_version'],VERSION)

    def test_original_integer_boundaries_and_every_output_score(self):
        boundaries = [(0,0,1),(.9,2,1),(12.999,9,1),(13,10,2),
            (22.999,19,2),(23,20,3),(27.999,29,3),(28,30,4),
            (39.999,39,4),(40,40,5),(45.999,49,5),(46,50,6),(100,60,6)]
        for response, score, level in boundaries:
            with self.subTest(response=response):
                self.assertEqual(score_from_response(response),score)
                self.assertEqual(classification(score)['moisture_level'],level)
        scores=[]
        for i in range(100001):
            response=i/1000
            score=score_from_response(response);scores.append(score)
            index=math.floor(response)
            expected=1 if index<=12 else 2 if index<=22 else 3 if index<=27 else 4 if index<=39 else 5 if index<=45 else 6
            self.assertEqual(classification(score)['moisture_level'],expected)
        self.assertEqual(set(scores),set(range(61)))
        self.assertEqual(scores,sorted(scores))

    def test_invalid_values_do_not_become_zero(self):
        for value in (-1,100.1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):score_from_response(value)
        for value in (-1,61,.1,True):
            with self.assertRaises(ValueError):classification(value)
        for args in ((2540,2540,44),(2540,0,44),(2540,500,44),(2540,2506,10)):
            with self.assertRaises(ValueError):estimate(*args,VERSION)

    def test_equivalent_dividers_and_legacy_scales(self):
        for response in (.5,12.999,13,22.999,23,28,40,46,75,99):
            results=[]
            for divider in (11,22,44):
                baseline=(500+170)*divider/11-170
                count=(500*(1-response/100)+170)*divider/11-170
                r=estimate(baseline,count,divider,VERSION)
                results.append((r['normalized_score'],r['moisture_level'],r['estimated_state']))
                self.assertEqual(r['score_max'],60)
                self.assertEqual(r['estimation_version'],VERSION)
            self.assertEqual(len(set(results)),1)
        self.assertEqual(estimate(2538,2506,44,OLD_VERSION)['normalized_score'],3)
        self.assertEqual(estimate(2538,2506,44,DISPLAY_VERSION)['normalized_score'],24)
        self.assertEqual(estimate(2538,2506,44,VERSION)['normalized_score'],3)


class Score60FlowTests(unittest.TestCase):
    setUp=f.ApiDatabaseTests.setUp
    tearDown=f.ApiDatabaseTests.tearDown

    def test_v1_and_v2_persist_separately_with_same_recommendations(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                aid=(await c.post('/api/skin/analyses',json={'moisture_source':'none'})).json()['id']
                saved_results=[];previews=[]
                for version in (LEGACY_VERSION,VERSION):
                    measured=actual(True);measured['normalization_version']=version
                    response=await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':measured})
                    self.assertEqual(response.status_code,200,response.text)
                    saved_results.append((measured,response.json()))
                    analysis=(await c.get(f'/api/skin/analyses/{aid}')).json()
                    preview=await c.post('/api/cosmetics/recommendations/preview',json=dict(scores=analysis['scores'],
                        score_semantics='photo_v1',moisture_analysis_id=aid,moisture_measurement_id=measured['measurement_id'],
                        avoid_dryness_triggers=True))
                    self.assertEqual(preview.status_code,200,preview.text);previews.append(preview.json())
                self.assertEqual([r['normalized_score'] for _,r in saved_results],[1,3])
                self.assertEqual(previews[0]['recommendations'],previews[1]['recommendations'])
                self.assertEqual(previews[0]['applied_exclusions'],previews[1]['applied_exclusions'])
                for measured,receipt in saved_results:
                    again=await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':measured})
                    self.assertEqual(again.json(),receipt,'old saved score must not be silently reinterpreted')
        asyncio.run(flow())

    def test_six_levels_save_reload_recommend_and_ignore_client_tampering(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                # A valid small reaction must remain zero; failure has no receipt.
                for count,level in ((2538,1),(2215,2),(2032,3),(1850,4),(1687,5),(1322,6),(510,6)):
                    aid=(await c.post('/api/skin/analyses',json={'moisture_source':'none'})).json()['id']
                    measured=actual(True);measured['normalization_version']=VERSION
                    for sample in measured['samples']:sample['count']=count
                    body={'analysis_id':aid,'result':measured}
                    saved=await c.post('/api/skin/moisture/results',json=body)
                    self.assertEqual(saved.status_code,200,saved.text)
                    r=saved.json();score=r['normalized_score']
                    self.assertEqual(r['score_max'],60)
                    self.assertEqual(r['moisture_level'],level)
                    self.assertTrue(r['used_for_scoring'])
                    if count==2538:self.assertEqual(score,0)
                    duplicate=await c.post('/api/skin/moisture/results',json=body)
                    self.assertEqual(duplicate.json(),r)
                    analysis=(await c.get(f'/api/skin/analyses/{aid}')).json()
                    self.assertEqual(analysis['moisture_measurement']['moisture_level'],level)
                    self.assertEqual(next(s for s in analysis['scores'] if s['metric_code']=='moisture')['score'],score)
                    request=dict(scores=analysis['scores'],score_semantics='photo_v1',
                        moisture_analysis_id=aid,moisture_measurement_id=measured['measurement_id'],
                        avoid_dryness_triggers=True)
                    preview=await c.post('/api/cosmetics/recommendations/preview',json=request)
                    self.assertEqual(preview.status_code,200,preview.text)
                    result=preview.json();policy=result['hydration_policy']
                    self.assertEqual(policy['normalized_score'],score)
                    self.assertEqual(policy['moisture_level'],level)
                    self.assertEqual(policy['dryness_exclusion_enabled'],level<=2)
                    assessment=next(a for a in result['assessments'] if a['code']=='moisture')
                    self.assertEqual((assessment['score'],assessment['score_max'],assessment['moisture_level']),(score,60,level))
                    for fake in (0,60,100):
                        altered=copy.deepcopy(request)
                        for s in altered['scores']:
                            if s['metric_code']=='moisture':s.update(score=fake,category_name='양호')
                        response=await c.post('/api/cosmetics/recommendations/preview',json=altered)
                        self.assertEqual(response.status_code,200,response.text)
                        self.assertEqual(response.json(),result)
        asyncio.run(flow())
