"""Apply only the v7 observation migration, never pending legacy migrations."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from app.core.config import get_settings

PREVIOUS = 'ae596f5070ae'
TARGET = 'f0810a1b2c3d'

def main():
    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        heads = MigrationContext.configure(conn).get_current_heads()
    engine.dispose()
    if heads == (TARGET,):
        print('수분 측정 DB는 이미 v7입니다.'); return
    if heads != (PREVIOUS,):
        raise SystemExit('DB를 변경하지 않았습니다. 예상 이전 버전: ' + PREVIOUS +
                         '; 실제 버전: ' + ', '.join(heads) +
                         '. 이 출력을 공유해 주세요. 기존 마이그레이션을 임의로 건너뛰거나 stamp하지 마세요.')
    config = Config(str(ROOT / 'alembic.ini'))
    config.set_main_option('script_location', str(ROOT / 'alembic'))
    command.upgrade(config, TARGET)
    print('수분 측정 결과 테이블 적용 완료. 기존 피부 점수는 변경하지 않았습니다.')

if __name__ == '__main__': main()
