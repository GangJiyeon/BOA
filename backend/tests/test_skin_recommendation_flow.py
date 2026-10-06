"""실제 API/DB 흐름 검증. 정상 사진 점수는 CV 대역; 손상 사진은 실제 디코더 사용."""
import asyncio
import unittest
from unittest.mock import patch
import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session
import test_cosmetic_recommendation as f
from app.models.skin import SkinAnalysis
from app.main import app
from app.services.skin_analysis import AnalysisError
from app.services.errors import ErrorCode


class SkinRecommendationFlowTests(unittest.TestCase):
    setUp = f.ApiDatabaseTests.setUp
    tearDown = f.ApiDatabaseTests.tearDown

    async def flow(self, moisture=None):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
            data={'moisture_source': 'none' if moisture is None else 'manual'}
            if moisture is not None: data['moisture_score']=str(moisture)
            analysis=await c.post('/api/skin/analyses/debug', data=data,
                                  files={'file':('face.png',b'cv-test-double','image/png')})
            if analysis.status_code != 201: return analysis,None
            result=await c.post('/api/cosmetics/recommendations/preview',json={'scores':analysis.json()['scores']})
            return analysis,result

    def test_analyze_save_then_recommend_moisture_without_duplicate_save(self):
        with patch('app.api.routes.skin.skin_analysis.analyze_image_detail',
                   return_value=({'redness':15,'brightness':71,'trouble':92,'uniformity':91},{})):
            analysis,result=asyncio.run(self.flow(20))
        self.assertEqual(analysis.status_code,201)
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['recommendations'][0]['matches'][0]['metric_code'],'moisture')
        self.assertEqual(result.json()['deferred_metrics'],['trouble'])
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(SkinAnalysis)),1)

    def test_sensorless_photo_scores_unchanged_and_recommendation_deferred(self):
        scores={'redness':15,'brightness':71,'trouble':92,'uniformity':91}
        with patch('app.api.routes.skin.skin_analysis.analyze_image_detail',return_value=(scores,{})):
            analysis,result=asyncio.run(self.flow())
        self.assertEqual({r['metric_code']:r['score'] for r in analysis.json()['scores']},scores)
        self.assertEqual(result.json()['missing_metrics'],['moisture'])
        self.assertEqual(result.json()['recommendations'],[])
        self.assertEqual(result.json()['target_count'],1)

    def test_corrupt_photo_uses_real_decoder_and_no_save(self):
        analysis,result=asyncio.run(self.flow())
        self.assertEqual(analysis.status_code,400)
        self.assertEqual(analysis.json()['detail']['code'],ErrorCode.IMAGE_UNREADABLE)
        self.assertIsNone(result)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(SkinAnalysis)),0)

    def test_face_detection_error_retains_message(self):
        with patch('app.api.routes.skin.skin_analysis.analyze_image_detail',
                   side_effect=AnalysisError('얼굴을 찾지 못했습니다',code=ErrorCode.FACE_NOT_FOUND)):
            analysis,result=asyncio.run(self.flow())
        self.assertEqual(analysis.status_code,400)
        self.assertEqual(analysis.json()['detail']['message'],'얼굴을 찾지 못했습니다')
        self.assertIsNone(result)

    def test_app_lifespan_starts_and_stops_scheduler(self):
        async def run():
            async with app.router.lifespan_context(app):
                pass
        asyncio.run(run())
