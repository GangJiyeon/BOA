"""비회원 하루 횟수 제한 (한국 시간 자정 기준)

분석 결과 테이블에서 오늘 생긴 행을 셈 (별도 카운터 없음)
회원·키오스크는 제한 없음
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import column, func, inspect, select, table
from sqlalchemy.orm import Session

from app.api.deps import Actor
from app.core.config import get_settings
from app.models import GuestSession, SkinAnalysis

QuotaKind = Literal["skin", "hair"]
KST = timezone(timedelta(hours=9))

# 헤어 테이블은 헤어 파트 머지 전이라 통합 ERD 이름 사용 (바뀌면 여기만 수정)
HAIR_TABLE = "hair_rec_run"
_hair = table(HAIR_TABLE, column("guest_id"), column("created_at"))
_skin = SkinAnalysis.__table__
_sessions = GuestSession.__table__

# 기능별 (guest_id 칼럼, 생성 시각 칼럼)
SOURCES = {
    "skin": (_skin.c.guest_id, _skin.c.analyzed_at),
    "hair": (_hair.c.guest_id, _hair.c.created_at),
}


@dataclass(frozen=True)
class Usage:
    limit: int | None  # None이면 제한 없음
    used: int

    @property
    def remaining(self) -> int | None:
        return None if self.limit is None else max(self.limit - self.used, 0)


def _today_start() -> datetime:
    return datetime.combine(datetime.now(KST).date(), time.min, tzinfo=KST)


def _limit(kind: QuotaKind) -> int:
    settings = get_settings()
    return settings.guest_daily_limit_skin if kind == "skin" else settings.guest_daily_limit_hair


def _available(db: Session, kind: QuotaKind) -> bool:
    """헤어 테이블이 없는 DB(헤어 파트 머지 전)에서는 세지 않음"""
    return kind == "skin" or inspect(db.get_bind()).has_table(HAIR_TABLE)


def _count(db: Session, kind: QuotaKind, *, guest_id=None, ip_hash: str | None = None) -> int:
    """오늘 생긴 행 수, guest_id 또는 같은 ip_hash 세션 전체 기준"""
    guest_col, created_col = SOURCES[kind]
    stmt = select(func.count()).select_from(guest_col.table).where(created_col >= _today_start())
    if guest_id is not None:
        stmt = stmt.where(guest_col == guest_id)
    else:
        stmt = stmt.join(_sessions, _sessions.c.id == guest_col).where(_sessions.c.ip_hash == ip_hash)
    return db.scalar(stmt) or 0


def get_usage(db: Session, actor: Actor, kind: QuotaKind) -> Usage:
    """세션 기준 오늘 사용량 (IP 합산은 응답에 노출 안 함)"""
    if actor.kind != "guest" or _limit(kind) == 0 or not _available(db, kind):
        return Usage(limit=None, used=0)
    return Usage(limit=_limit(kind), used=_count(db, kind, guest_id=actor.guest_id))


def check_quota(db: Session, actor: Actor, kind: QuotaKind) -> None:
    """분석 직전에 호출, 비회원이 오늘 한도를 넘으면 429"""
    usage = get_usage(db, actor, kind)
    if usage.limit is None:
        return
    if usage.used >= usage.limit:
        raise HTTPException(
            429,
            {
                "code": "GUEST_DAILY_LIMIT",
                "message": "오늘 비회원 이용 횟수를 모두 사용했습니다. 가입하면 계속 이용할 수 있어요",
            },
        )

    ip_limit = get_settings().ip_daily_limit
    session = db.get(GuestSession, actor.guest_id)
    # 키오스크 세션은 ip_hash 없음
    if ip_limit and session is not None and session.ip_hash:
        if _count(db, kind, ip_hash=session.ip_hash) >= ip_limit:
            raise HTTPException(
                429,
                {"code": "IP_DAILY_LIMIT", "message": "오늘 이 네트워크의 이용 횟수를 모두 사용했습니다"},
            )
