"""회원 이력의 실제 DB 필터·정렬·페이지 분할·이관·인증 회귀 테스트."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite://")

import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session
from app.api.deps import Actor, get_actor
from app.api.routes import me
from app.core.security import create_access_token
from app.models import FaceAnalysis, HairRecRun, SkinAnalysis, User
from app.services import guest
import test_analysis_ownership as fixture


class HistoryTests(unittest.TestCase):
    def setUp(self):
        fixture.OwnershipTests.setUp(self)
        self.app.include_router(me.router, prefix='/api')
        self.base = datetime(2026, 11, 14, 1, tzinfo=UTC)
        with Session(self.engine) as db:
            db.add_all([User(id=i, email=f'member{i}@example.com', language='ko') for i in (7, 8)])
            db.commit()

    tearDown = fixture.OwnershipTests.tearDown

    def seed(self, skins=0, hairs=0, user_id=7, guest_id=None):
        with Session(self.engine) as db:
            for i in range(skins):
                db.add(SkinAnalysis(user_id=user_id, guest_id=guest_id, moisture_source='none',
                    logic_version='v1', analyzed_at=self.base + timedelta(minutes=i)))
            for i in range(hairs):
                face = FaceAnalysis(user_id=user_id, guest_id=guest_id, sex='male', face_shape='계란형')
                db.add(face); db.flush()
                db.add(HairRecRun(user_id=user_id, guest_id=guest_id, face_analysis_id=face.id,
                    created_at=self.base + timedelta(minutes=i), top_n=5))
            db.commit()

    def page(self, query=''):
        response = self.client.get('/api/me/analyses' + query)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_empty_and_authentication(self):
        value = self.page()
        self.assertEqual(value, dict(items=[], limit=20, offset=0, has_more=False))
        for actor in (Actor(kind='anonymous'), Actor(kind='guest', guest_id=self.guest_id), Actor(kind='kiosk', kiosk_id=1)):
            self.actor = actor
            self.assertEqual(self.client.get('/api/me/analyses').status_code, 401)

    def test_only_current_members_rows_and_safe_metadata(self):
        self.seed(skins=2, hairs=1)
        self.seed(skins=3, hairs=2, user_id=8)
        self.seed(skins=1, hairs=1, user_id=None, guest_id=uuid4())
        own = self.page('?user_id=8')['items']
        self.assertEqual(len(own), 3)
        self.assertEqual({row['kind'] for row in own}, {'skin', 'hair'})
        self.assertTrue(all(set(row) == {'kind', 'id', 'created_at'} for row in own))
        self.actor = Actor(kind='member', user_id=8)
        other = self.page()['items']
        self.assertEqual(len(other), 5)
        self.assertTrue({(r['kind'], r['id']) for r in own}.isdisjoint({(r['kind'], r['id']) for r in other}))

    def test_combined_order_paging_and_no_duplicates_at_same_time(self):
        self.seed(skins=24, hairs=24)
        first = self.page('?limit=20&offset=0')
        second = self.page('?limit=20&offset=20')
        third = self.page('?limit=20&offset=40')
        self.assertTrue(first['has_more']); self.assertTrue(second['has_more']); self.assertFalse(third['has_more'])
        items = first['items'] + second['items'] + third['items']
        self.assertEqual(len(items), 48)
        self.assertEqual(len({(r['kind'], r['id']) for r in items}), 48)
        self.assertEqual([r['created_at'] for r in items], sorted([r['created_at'] for r in items], reverse=True))
        self.assertEqual(items[0]['kind'], 'hair')
        self.assertEqual(self.page('?offset=500')['items'], [])

    def test_filter_and_parameter_validation(self):
        self.seed(skins=3, hairs=2)
        for kind, count in [('skin', 3), ('hair', 2)]:
            items = self.page(f'?kind={kind}')['items']
            self.assertEqual(len(items), count)
            self.assertTrue(all(r['kind'] == kind for r in items))
        for query in ('?kind=studio', '?limit=0', '?limit=51', '?offset=-1'):
            self.assertEqual(self.client.get('/api/me/analyses' + query).status_code, 422)

    def test_transferred_guest_records_survive_fresh_request(self):
        self.seed(skins=1, hairs=1, user_id=None, guest_id=self.guest_id)
        self.assertEqual(self.page()['items'], [])
        with Session(self.engine) as db:
            from app.models import GuestSession
            guest.transfer_to_user(db, db.get(GuestSession, self.guest_id), 7)
            db.commit()
        self.app.dependency_overrides.pop(get_actor)
        self.client.cookies.set('access_token', create_access_token(7))
        first = self.page()['items']
        self.assertEqual(len(first), 2)
        self.assertEqual(self.page()['items'], first)
        for item in first:
            prefix = '/api/skin/analyses/' if item['kind'] == 'skin' else '/api/hair/recommend/'
            self.assertEqual(self.client.get(prefix + str(item['id'])).status_code, 200)

    def test_deleted_member_cannot_read_history(self):
        self.app.dependency_overrides.pop(get_actor)
        self.client.cookies.set('access_token', create_access_token(999))
        self.assertEqual(self.client.get('/api/me/analyses').status_code, 401)


if __name__ == '__main__':
    unittest.main()
