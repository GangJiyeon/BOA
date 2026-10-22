import asyncio
import unittest
from unittest.mock import patch
import httpx
import test_cosmetic_recommendation as fixture
from app.main import app
from app.core.config import get_settings


def measurement(**changes):
    value = dict(protocol_version=1, source='ble_sensor', status='valid', raw_value=1200,
                 unit='fdc2112_count', sequence=1, device_uptime_ms=500,
                 received_at='2026-10-22T08:00:00Z')
    value.update(changes)
    return value


class MoistureTests(unittest.TestCase):
    setUp = fixture.ApiDatabaseTests.setUp
    tearDown = fixture.ApiDatabaseTests.tearDown

    def submit(self, value, analysis_id=None):
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                return await client.post('/api/skin/moisture/validate', json={'analysis_id':analysis_id,'measurement':value})
        return asyncio.run(run())

    def test_accepts_raw_without_score_or_persistence(self):
        r = self.submit(measurement())
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['persisted'])
        self.assertFalse(r.json()['used_for_scoring'])
        self.assertEqual(r.json()['measurement']['raw_value'],1200)

    def test_invalid_values(self):
        for fields in [dict(raw_value=-1),dict(raw_value=4096),dict(raw_value=True),dict(raw_value=1.1),
                       dict(raw_value='12'),dict(raw_value=None),dict(status='sensor_error'),
                       dict(protocol_version=2),dict(sequence=-1),dict(device_uptime_ms=2**32),
                       dict(source='sensor'),dict(unit='%'),dict(received_at='2026-10-22T08:00:00'),dict(score=20)]:
            with self.subTest(fields=fields): self.assertEqual(self.submit(measurement(**fields)).status_code,422)

    def test_fault_telemetry_requires_null(self):
        self.assertEqual(self.submit(measurement(status='sensor_error',raw_value=None)).status_code,200)

    def test_simulation_default_denied_and_explicit_dev_enabled(self):
        settings = get_settings()
        with patch.object(settings,'moisture_allow_simulation',False):
            for source in ['mock','ble_simulation']: self.assertEqual(self.submit(measurement(source=source)).status_code,403)
        with patch.object(settings,'moisture_allow_simulation',True):
            self.assertEqual(self.submit(measurement(source='mock')).status_code,200)

    def test_missing_analysis(self):
        self.assertEqual(self.submit(measurement(),99999).status_code,404)

    def test_existing_analysis_and_recommendation_unchanged(self):
        async def flow():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
                before = await c.post('/api/skin/analyses',json={'moisture_source':'manual','moisture_score':25})
                self.assertEqual(before.status_code,201)
                analysis_id = before.json()['id']
                rec1 = await c.post('/api/cosmetics/recommendations/preview',json={'scores':before.json()['scores']})
                r = await c.post('/api/skin/moisture/validate',json={'analysis_id':analysis_id,'measurement':measurement()})
                self.assertEqual(r.status_code,200)
                self.assertEqual(r.json()['analysis_id'],analysis_id)
                after = await c.get(f'/api/skin/analyses/{analysis_id}')
                self.assertEqual(before.json(),after.json())
                rec2 = await c.post('/api/cosmetics/recommendations/preview',json={'scores':after.json()['scores']})
                self.assertEqual(rec1.json()['recommendations'],rec2.json()['recommendations'])
        asyncio.run(flow())
