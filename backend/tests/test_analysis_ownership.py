"""인증된 소유자 저장·조회·이관 및 비회원 제한 회귀 테스트.

CV/랜드마크만 대역으로 바꾸고 API와 DB 저장은 실제로 실행한다.
"""
import os
os.environ.setdefault('DATABASE_URL', 'sqlite://')

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import Actor, get_actor
from app.api.routes import hair, moisture, skin
from app.db.base import Base
from app.db.session import get_db
from app.models import (FaceAnalysis, GuestSession, HairRecommendation, HairRecRun,
                        HairStyleCatalog, Image, Kiosk, SkinAnalysis, SkinMetric,
                        SkinMetricCategory, SkinScore, Terms, User)
from app.models.moisture import MoistureObservation
from app.services import guest
from scripts.seed_skin_metrics import seed_metrics


@compiles(JSONB, 'sqlite')
def sqlite_jsonb(type_, compiler, **kw):
    return 'JSON'


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        models = (User, Terms, Kiosk, GuestSession, Image, SkinMetric, SkinMetricCategory,
                  SkinAnalysis, SkinScore, MoistureObservation, FaceAnalysis,
                  HairStyleCatalog, HairRecRun, HairRecommendation)
        Base.metadata.create_all(self.engine, tables=[m.__table__ for m in models])
        self.guest_id = uuid4()
        with Session(self.engine) as db:
            seed_metrics(db)
            db.add(GuestSession(id=self.guest_id, expires_at=datetime.now(UTC) + timedelta(days=7)))
            db.commit()
        self.actor = Actor(kind='member', user_id=7)
        self.app = FastAPI()
        for router in (skin.router, hair.router, moisture.router):
            self.app.include_router(router, prefix='/api')
        def database():
            with Session(self.engine) as db:
                yield db
        self.app.dependency_overrides[get_db] = database
        self.app.dependency_overrides[get_actor] = lambda: self.actor
        self.client = TestClient(self.app)
        self.photo = patch.object(skin.skin_analysis, 'analyze_image_detail', return_value=(
            dict(redness=20, brightness=70, trouble=20, uniformity=70), {}))
        self.photo_mock = self.photo.start()
        self.face = patch.object(hair, 'analyze_face_shape', return_value=dict(
            face_shape='계란형', top2=None, confidence=.9, ratios={}))
        self.face.start()
        self.landmarks = patch.object(hair, 'extract_landmarks_from_bytes', return_value={})
        self.landmarks.start()

    def tearDown(self):
        self.landmarks.stop(); self.face.stop(); self.photo.stop()
        self.client.close()
        self.engine.dispose()

    def skin(self, **body):
        response = self.client.post('/api/skin/analyses', json={'moisture_source': 'none', **body})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['id']

    def face_analysis(self, photos=False):
        if photos:
            response = self.client.post('/api/hair/face-analysis/photos',
                data={'sex': 'male', 'user_id': '999', 'guest_id': str(uuid4())},
                files=[('photos', ('face.jpg', b'photo', 'image/jpeg'))])
        else:
            response = self.client.post('/api/hair/face-analysis', json=dict(
                sex='male', landmark_sets=[{}], user_id=999, guest_id=str(uuid4())))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['id']

    def test_skin_json_and_frontend_photo_save_authenticated_owner(self):
        ids = [self.skin(guest_id=str(uuid4()))]
        response = self.client.post('/api/skin/analyses/debug', files={'file': ('face.jpg', b'photo', 'image/jpeg')})
        self.assertEqual(response.status_code, 201, response.text)
        ids.append(response.json()['id'])
        with Session(self.engine) as db:
            for aid in ids:
                row = db.get(SkinAnalysis, aid)
                self.assertEqual(row.user_id, 7)
                self.assertIsNone(row.guest_id)
        self.assertEqual(self.client.get(f'/api/skin/analyses/{ids[0]}').status_code, 200)
        self.actor = Actor(kind='member', user_id=8)
        self.assertEqual(self.client.get(f'/api/skin/analyses/{ids[0]}').status_code, 404)
        self.assertEqual(self.client.get(f'/api/skin/analyses/{ids[0]}').json(),
                         self.client.get('/api/skin/analyses/999999').json())

    def test_guest_skin_limit_and_failed_photo_not_counted(self):
        self.actor = Actor(kind='guest', guest_id=self.guest_id)
        bad = self.client.post('/api/skin/analyses/debug', files={'file': ('x.txt', b'x', 'text/plain')})
        self.assertEqual(bad.status_code, 400)
        for _ in range(3):
            self.skin()
        response = self.client.post('/api/skin/analyses', json={})
        self.assertEqual(response.status_code, 429, response.text)
        self.assertEqual(response.json()['detail']['code'], 'GUEST_DAILY_LIMIT')
        with Session(self.engine) as db:
            rows = db.scalars(select(SkinAnalysis)).all()
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(r.user_id is None and r.guest_id == self.guest_id for r in rows))

    def test_both_hair_inputs_and_recommendation_use_actor(self):
        for photos in (False, True):
            aid = self.face_analysis(photos)
            response = self.client.post('/api/hair/recommend', json=dict(
                face_analysis_id=aid, user_id=999, guest_id=str(uuid4())))
            self.assertEqual(response.status_code, 201, response.text)
            rid = response.json()['run_id']
            with Session(self.engine) as db:
                self.assertEqual(db.get(FaceAnalysis, aid).user_id, 7)
                self.assertEqual(db.get(HairRecRun, rid).user_id, 7)
                self.assertIsNone(db.get(HairRecRun, rid).guest_id)
            self.assertEqual(self.client.get(f'/api/hair/recommend/{rid}').status_code, 200)
            self.actor = Actor(kind='member', user_id=8)
            self.assertEqual(self.client.get(f'/api/hair/face-analysis/{aid}').status_code, 404)
            self.assertEqual(self.client.get(f'/api/hair/recommend/{rid}').status_code, 404)
            self.assertEqual(self.client.post('/api/hair/recommend', json={'face_analysis_id': aid}).status_code, 404)
            self.actor = Actor(kind='member', user_id=7)

    def test_guest_hair_counts_recommendation_once_not_each_photo(self):
        self.actor = Actor(kind='guest', guest_id=self.guest_id)
        aid = self.face_analysis(photos=True)
        for _ in range(3):
            response = self.client.post('/api/hair/recommend', json={'face_analysis_id': aid})
            self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.client.post('/api/hair/recommend', json={'face_analysis_id': aid}).status_code, 429)
        self.assertEqual(self.client.post('/api/hair/face-analysis/photos', data={'sex': 'male'},
            files=[('photos', ('face.jpg', b'photo', 'image/jpeg'))]).status_code, 429)

    def test_transferred_guest_cannot_read_member_result(self):
        self.actor = Actor(kind='guest', guest_id=self.guest_id)
        aid = self.skin()
        fid = self.face_analysis()
        with Session(self.engine) as db:
            guest.transfer_to_user(db, db.get(GuestSession, self.guest_id), 7)
            db.commit()
        self.assertEqual(self.client.get(f'/api/skin/analyses/{aid}').status_code, 404)
        self.assertEqual(self.client.get(f'/api/hair/face-analysis/{fid}').status_code, 404)
        self.actor = Actor(kind='member', user_id=7)
        self.assertEqual(self.client.get(f'/api/skin/analyses/{aid}').status_code, 200)
        self.assertEqual(self.client.get(f'/api/hair/face-analysis/{fid}').status_code, 200)

    def test_anonymous_and_kiosk_without_session_rejected_before_analysis(self):
        for actor in (Actor(kind='anonymous'), Actor(kind='kiosk', kiosk_id=1)):
            self.actor = actor
            self.assertEqual(self.client.post('/api/skin/analyses', json={}).status_code, 403)
            self.assertEqual(self.client.post('/api/skin/analyses/debug', files={'file': ('a.jpg', b'a', 'image/jpeg')}).status_code, 403)
            self.assertEqual(self.client.post('/api/hair/face-analysis', json={'sex': 'male', 'landmark_sets': [{}]}).status_code, 403)
        self.photo_mock.assert_not_called()

    def test_moisture_write_and_idempotent_read_check_owner(self):
        aid = self.skin()
        payload = dict(measurement_id=str(uuid4()), algorithm_version='cheek-auto-v1',
            site='left_cheek', measured_at='2026-10-27T01:00:00Z', baseline=500,
            contact_threshold=2, release_threshold=1,
            samples=[dict(sequence=i, uptime_ms=1000+i*100, count=400+i%2) for i in range(31)])
        body = {'analysis_id': aid, 'result': payload}
        self.actor = Actor(kind='member', user_id=8)
        self.assertEqual(self.client.post('/api/skin/moisture/results', json=body).status_code, 404)
        self.actor = Actor(kind='member', user_id=7)
        saved = self.client.post('/api/skin/moisture/results', json=body)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(self.client.post('/api/skin/moisture/results', json=body).json(), saved.json())
        self.actor = Actor(kind='member', user_id=8)
        self.assertEqual(self.client.post('/api/skin/moisture/results', json=body).status_code, 404)

    def test_member_and_active_kiosk_not_subject_to_guest_limit(self):
        for actor in (Actor(kind='member', user_id=7),
                      Actor(kind='kiosk', kiosk_id=1, guest_id=self.guest_id)):
            self.actor = actor
            for _ in range(4):
                self.skin()

    def test_guest_ip_limit_covers_other_sessions(self):
        from app.core.config import get_settings
        settings = get_settings()
        other_id = uuid4()
        with Session(self.engine) as db:
            db.get(GuestSession, self.guest_id).ip_hash = 'shared'
            db.add(GuestSession(id=other_id, ip_hash='shared',
                expires_at=datetime.now(UTC) + timedelta(days=7)))
            db.add(SkinAnalysis(guest_id=other_id, moisture_source='none', logic_version='test'))
            db.commit()
        self.actor = Actor(kind='guest', guest_id=self.guest_id)
        with patch.object(settings, 'ip_daily_limit', 1):
            response = self.client.post('/api/skin/analyses', json={})
        self.assertEqual(response.status_code, 429, response.text)
        self.assertEqual(response.json()['detail']['code'], 'IP_DAILY_LIMIT')

    def test_deleted_user_token_rejected_by_real_actor_dependency(self):
        from app.core.security import create_access_token
        self.app.dependency_overrides.pop(get_actor)
        self.client.cookies.set('access_token', create_access_token(999))
        response = self.client.post('/api/skin/analyses', json={})
        self.assertEqual(response.status_code, 401, response.text)


if __name__ == '__main__':
    unittest.main()
