import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_cosmetic_recommendation  # establish isolated test settings before app import
import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import Actor, get_actor
from app.api.routes import studio
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import HairRender, HairStyleCatalog
from app.models.hair import Sex


@compiles(JSONB, 'sqlite')
def sqlite_jsonb(type_, compiler, **kw):
    return 'JSON'


def seed_style(db):
    db.add(HairStyleCatalog(style_id='bob',name='단발',sex=Sex.UNISEX,
        length='short',texture='straight',face_fit={}))
    db.commit()


class StudioIntegrationTests(unittest.TestCase):
    def test_create_poll_and_ownership_with_mocked_ai(self):
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(engine)
        with Session(engine) as db:seed_style(db)
        def session():
            with Session(engine) as db:yield db
        app.dependency_overrides[get_db]=session
        app.dependency_overrides[get_actor]=lambda:Actor(kind='member',user_id=7)
        def finish(render_id,photo):
            self.assertEqual(photo,b'photo-bytes')
            with Session(engine) as db:
                db.get(HairRender,render_id).status='done';db.commit()
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                with patch.object(studio,'get_settings',return_value=SimpleNamespace(gemini_api_key='test-only')),patch.object(studio.quota,'check_quota') as quota,patch.object(studio.hair_studio,'decode_image',return_value=object()),patch.object(studio.hair_studio,'landmarks'),patch.object(studio.hair_studio,'process_render',side_effect=finish):
                    created=await client.post('/api/studio/hair-renders',data={'style_id':'bob'},files={'photo':('face.jpg',b'photo-bytes','image/jpeg')})
                    self.assertEqual(created.status_code,202,created.text)
                    self.assertEqual(created.json()['status'],'pending')
                    self.assertEqual(quota.call_args.args[2],'studio')
                    render_id=created.json()['id']
                done=await client.get(f'/api/studio/hair-renders/{render_id}')
                self.assertEqual(done.status_code,200,done.text)
                self.assertEqual(done.json()['status'],'done')
                self.assertTrue(done.json()['mid']['image'].endswith('/mid.jpg'))
                self.assertIsNone(done.json()['light'])
                self.assertIsNone(done.json()['brown'])
                app.dependency_overrides[get_actor]=lambda:Actor(kind='member',user_id=8)
                self.assertEqual((await client.get(f'/api/studio/hair-renders/{render_id}')).status_code,404)
        try:asyncio.run(run())
        finally:app.dependency_overrides.clear();engine.dispose()

    def test_upgrade_heads_preserves_hydration_branch_and_existing_rows(self):
        with TemporaryDirectory() as folder:
            url='sqlite:///'+str(Path(folder)/'integration.db')
            engine=create_engine(url)
            Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name!='hair_renders'])
            with Session(engine) as db:seed_style(db)
            with engine.begin() as db:
                db.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
                db.execute(text("INSERT INTO alembic_version VALUES ('f0910a1b2c3d')"))
            config=Config(str(Path(__file__).parents[1]/'alembic.ini'))
            with patch('app.core.config.get_settings',return_value=SimpleNamespace(database_url=url)):
                command.upgrade(config,'heads')
            self.assertIn('hair_renders',inspect(engine).get_table_names())
            with engine.connect() as db:
                self.assertEqual(set(db.scalars(text('SELECT version_num FROM alembic_version'))),{'f1010a1b2c3d'})
                self.assertEqual(db.scalar(text('SELECT count(*) FROM hair_style_catalog')),1)
            engine.dispose()

    def test_upgrade_from_team_studio_head_preserves_hair_rows(self):
        with TemporaryDirectory() as folder:
            url='sqlite:///'+str(Path(folder)/'team-first.db')
            engine=create_engine(url)
            Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name!='moisture_observations'])
            with Session(engine) as db:
                seed_style(db)
                db.add(HairRender(style_id='bob', status='done', asset_dir='existing-team-render', hair_hex='#342820'))
                db.commit()
            with engine.begin() as db:
                db.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
                db.execute(text("INSERT INTO alembic_version VALUES ('b2c3d4e5f6a7')"))
            config=Config(str(Path(__file__).parents[1]/'alembic.ini'))
            with patch('app.core.config.get_settings',return_value=SimpleNamespace(database_url=url)):
                command.upgrade(config,'head')
                command.upgrade(config,'head')
            self.assertIn('moisture_observations',inspect(engine).get_table_names())
            with engine.connect() as db:
                self.assertEqual(set(db.scalars(text('SELECT version_num FROM alembic_version'))),{'f1010a1b2c3d'})
                self.assertEqual(db.scalar(text('SELECT hair_hex FROM hair_renders')),'#342820')
                self.assertEqual(db.scalar(text('SELECT count(*) FROM hair_style_catalog')),1)
            engine.dispose()
