#!/bin/sh
set -e

# 로컬 개발에서는 DB 스키마를 SQL로 직접 관리하므로 마이그레이션을 실행하지 않는다.
# 서버 배포 이후 Alembic을 도입하면 여기서 `alembic upgrade head`를 다시 실행한다.

exec "$@"
