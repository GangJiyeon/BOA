import asyncio
import copy
import unittest
from uuid import uuid4
import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session
import test_cosmetic_recommendation as fixture
from app.main import app
from app.models.moisture import MoistureObservation


def result():
    return dict(measurement_id=str(uuid4()), algorithm_version='cheek-auto-v1', site='left_cheek',
                measured_at='2026-10-27T01:00:00Z', baseline=500,
                contact_threshold=2, release_threshold=1,
                samples=[dict(sequence=i, uptime_ms=1000+i*100, count=400+i%2) for i in range(31)])


class CompletedTests(unittest.TestCase):
    setUp = fixture.ApiDatabaseTests.setUp
    tearDown = fixture.ApiDatabaseTests.tearDown

    def test_save_retry_read_and_score_isolation(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                created=await c.post('/api/skin/analyses',json={'moisture_source':'manual','moisture_score':25})
                self.assertEqual(created.status_code,201)
                aid=created.json()['id']; payload=result()
                body={'analysis_id':aid,'result':payload}
                saved=await c.post('/api/skin/moisture/results',json=body)
                self.assertEqual(saved.status_code,200,saved.text)
                self.assertTrue(saved.json()['persisted']);self.assertFalse(saved.json()['used_for_scoring'])
                self.assertEqual(saved.json()['sample_count'],31)
                again=await c.post('/api/skin/moisture/results',json=body)
                self.assertEqual(saved.json(),again.json())
                fetched=await c.get(f'/api/skin/analyses/{aid}')
                self.assertEqual(fetched.json()['scores'],created.json()['scores'])
                self.assertEqual(fetched.json()['moisture_measurement'],saved.json())
                changed=copy.deepcopy(body);changed['result']['samples'][0]['count']=401
                self.assertEqual((await c.post('/api/skin/moisture/results',json=changed)).status_code,409)
                other=await c.post('/api/skin/analyses',json={'moisture_source':'none'})
                changed=copy.deepcopy(body);changed['analysis_id']=other.json()['id']
                self.assertEqual((await c.post('/api/skin/moisture/results',json=changed)).status_code,409)
                with Session(self.engine) as db:self.assertEqual(db.scalar(select(func.count()).select_from(MoistureObservation)),1)
                old=result();old['measured_at']='2026-10-26T01:00:00Z'
                self.assertEqual((await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':old})).status_code,200)
                fetched=await c.get(f'/api/skin/analyses/{aid}')
                self.assertEqual(fetched.json()['moisture_measurement']['measurement_id'],payload['measurement_id'])
        asyncio.run(flow())

    def test_rejects_invalid_and_missing_analysis(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                aid=(await c.post('/api/skin/analyses',json={'moisture_source':'none'})).json()['id']
                cases=[]
                for k,v in [('site','finger'),('algorithm_version','anything'),('baseline',0),('samples',result()['samples'][:20]),('source','mock'),('score',20),('contact_threshold',-1),('release_threshold',2)]:
                    p=result();p[k]=v;cases.append(p)
                p=result();p['samples'][1]=p['samples'][0].copy();cases.append(p)
                p=result();p['samples'][10]['count']=500;cases.append(p)
                p=result();p['samples'][10]['count']=200;cases.append(p)
                p=result();p['samples'][10]['uptime_ms']+=500;cases.append(p)
                p=result();p['samples'][0]['count']=True;cases.append(p)
                for p in cases:
                    response=await c.post('/api/skin/moisture/results',json={'analysis_id':aid,'result':p})
                    self.assertEqual(response.status_code,422,response.text)
                self.assertEqual((await c.post('/api/skin/moisture/results',json={'analysis_id':9999,'result':result()})).status_code,404)
                with Session(self.engine) as db:self.assertEqual(db.scalar(select(func.count()).select_from(MoistureObservation)),0)
        asyncio.run(flow())

    def test_counters_wrap(self):
        from app.schemas.moisture import CompletedMoisture
        p=result()
        for i,s in enumerate(p['samples']):
            s['sequence']=(65520+i)%65536;s['uptime_ms']=(2**32-1500+i*100)%2**32
        self.assertEqual(CompletedMoisture.model_validate(p).statistics()['duration_ms'],3000)
