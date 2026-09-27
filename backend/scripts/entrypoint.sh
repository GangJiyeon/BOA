#!/bin/sh
set -e

# 서버를 띄우기 전에 DB 스키마를 최신 마이그레이션으로 맞춘다
alembic upgrade head

exec "$@"
