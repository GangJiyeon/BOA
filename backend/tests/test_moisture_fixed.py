import asyncio, copy, json, unittest
from pathlib import Path
from uuid import uuid4
import httpx
from sqlalchemy import select, func
from sqlalchemy.orm import Session
import test_cosmetic_recommendation as f
from app.main import app
from app.schemas.moisture import CompletedMoisture
from app.services.moisture_normalization import normalize
from app.models.skin import SkinScore, SkinMetric
from app.models.moisture import MoistureObservation


def actual(estimation=False):
    result=json.loads((Path(__file__).parents[2]/'fixtures/skin-fixed-result.json').read_text())
    result['measurement_id']=str(uuid4())
    if estimation:
        result['normalization_version']='hydration-estimate-pnj-2023-v1'
        result['sensor_profile']=dict(reference_divider=44,output_gain=16,offset=170,sensor_divider=2,verified=True)
    return result


class FixedWindowTests(unittest.TestCase):
    def test_actual_first_three_seconds_normalizes_to_26(self):
        r=CompletedMoisture.model_validate(actual())
        self.assertEqual(r.statistics()['duration_ms'],3000)
        self.assertEqual(normalize(r)['normalized_score'],26)
        self.assertEqual(normalize(r)['terminal_count'],2506)
        self.assertLess(r.samples[-1].uptime_ms-r.samples[0].uptime_ms,3000)

    def test_never_extends_or_accepts_missing_or_late_samples(self):
        for change in ('end','late','short','release','duplicate'):
            r=actual()
            if change=='end':r['window_end_uptime_ms']+=100
            if change=='late':r['samples'][-1]['uptime_ms']=r['window_end_uptime_ms']+1
            if change=='short':r['samples']=r['samples'][:25]
            if change=='release':
                for s in r['samples'][-11:]:s['count']=r['baseline']
            if change=='duplicate':r['samples'][5]=copy.deepcopy(r['samples'][4])
            with self.subTest(change=change),self.assertRaises(ValueError):CompletedMoisture.model_validate(r)

    def test_continuous_change_does_not_require_extra_stability(self):
        r=actual()
        for i,s in enumerate(r['samples']):s['count']=2520-i
        validated=CompletedMoisture.model_validate(r)
        self.assertGreater(normalize(validated)['normalized_score'],1)


class FixedApiTests(unittest.TestCase):
    setUp=f.ApiDatabaseTests.setUp
    tearDown=f.ApiDatabaseTests.tearDown
    def test_real_score_persisted_in_skin_analysis_and_used_by_recommendation(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                analysis=(await c.post('/api/skin/analyses',json={'moisture_source':'none'})).json();aid=analysis['id']
                r=actual(True);body={'analysis_id':aid,'result':r}
                saved=await c.post('/api/skin/moisture/results',json=body)
                self.assertEqual(saved.status_code,200,saved.text)
                receipt=saved.json();self.assertEqual(receipt['normalized_score'],3)
                self.assertTrue(receipt['used_for_scoring']);self.assertIsNone(receipt['calibrated_score'])
                self.assertEqual(receipt['score_category'],'개선 필요')
                self.assertEqual(receipt['scoring_status'],'experimental_estimate')
                fetched=(await c.get(f'/api/skin/analyses/{aid}')).json()
                self.assertEqual(fetched['moisture_source'],'sensor')
                moisture=next(s for s in fetched['scores'] if s['metric_code']=='moisture')
                self.assertEqual(moisture['score'],3);self.assertEqual(moisture['category_name'],'개선 필요')
                response=await c.post('/api/cosmetics/recommendations/preview',json={'scores':fetched['scores'],'score_semantics':'photo_v1'})
                self.assertEqual(response.status_code,200,response.text)
                data=response.json();self.assertNotIn('moisture',data['missing_metrics'])
                self.assertTrue(any(a['code']=='moisture' and a['needs_improvement'] for a in data['assessments']))
                self.assertTrue(any(m['metric_code']=='moisture' for p in data['recommendations'] for m in p['matches']))
                self.assertEqual((await c.post('/api/skin/moisture/results',json=body)).json(),receipt)
                with Session(self.engine) as db:
                    self.assertEqual(db.scalar(select(func.count()).select_from(MoistureObservation)),1)
                    metric=db.scalar(select(SkinMetric).where(SkinMetric.code=='moisture'))
                    scores=db.scalars(select(SkinScore).where(SkinScore.analysis_id==aid,SkinScore.metric_id==metric.id)).all()
                    self.assertEqual(len(scores),1);self.assertEqual(scores[0].score,3)
                # Another explicit measurement replaces the score without duplicates.
                newer=copy.deepcopy(r);newer['measurement_id']=str(uuid4())
                for s in newer['samples']:s['count']=2450
                updated=await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':newer})
                self.assertEqual(updated.status_code,200,updated.text)
                fetched=(await c.get(f'/api/skin/analyses/{aid}')).json()
                self.assertEqual(next(s['score'] for s in fetched['scores'] if s['metric_code']=='moisture'),updated.json()['normalized_score'])
        asyncio.run(flow())
