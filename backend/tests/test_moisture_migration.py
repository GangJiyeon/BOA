import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from sqlalchemy import create_engine, text, inspect


class MigrationTests(unittest.TestCase):
    def test_guard_upgrade_and_idempotency(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            url = 'sqlite:///' + str(Path(folder)/'test.db')
            engine = create_engine(url)
            with engine.begin() as c:
                c.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
                c.execute(text("INSERT INTO alembic_version VALUES ('e0710a1b2c3d')"))
                c.execute(text('CREATE TABLE skin_analyses (id INTEGER PRIMARY KEY)'))
                c.execute(text('INSERT INTO skin_analyses VALUES (7)'))
            env = {**os.environ, 'DATABASE_URL':url}
            def run():return subprocess.run([sys.executable, str(root/'scripts/upgrade_moisture_v7.py')],cwd=root,env=env,capture_output=True,text=True)
            refused=run();self.assertNotEqual(refused.returncode,0)
            self.assertNotIn('moisture_observations',inspect(engine).get_table_names())
            with engine.begin() as c:c.execute(text("UPDATE alembic_version SET version_num='ae596f5070ae'"))
            applied=run();self.assertEqual(applied.returncode,0,applied.stderr)
            self.assertIn('moisture_observations',inspect(engine).get_table_names())
            with engine.connect() as c:
                self.assertEqual(c.scalar(text('SELECT id FROM skin_analyses')),7)
                self.assertEqual(c.scalar(text('SELECT version_num FROM alembic_version')),'f0810a1b2c3d')
            self.assertEqual(run().returncode,0)
            engine.dispose()
