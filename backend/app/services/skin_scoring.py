"""점수 라벨링 서비스.

0~100으로 정규화된 지표 점수를 받아 해당하는 판정 구간을 찾고,
분석 1건(skin_analyses)과 지표별 점수(skin_scores)를 저장한다.

구간 경계값은 DB(skin_metric_categories)에서 읽으므로,
경계값을 조정해도 이 코드는 수정할 필요가 없다.
"""

from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SkinAnalysis, SkinMetric, SkinMetricCategory, SkinScore
from app.models.skin import MOISTURE_SOURCES

# 판정 기준 버전. 구간 경계값이나 점수 산출 방식을 바꾸면 이 값을 올린다.
LOGIC_VERSION = "v1"

# 수분 지표는 센서/직접입력이 없으면 빠질 수 있고, 나머지 4개는 사진에서 항상 나온다.
MOISTURE_CODE = "moisture"
REQUIRED_METRIC_CODES = ("redness", "brightness", "trouble", "uniformity")


class ScoringError(ValueError):
    """입력 점수나 기준 데이터가 잘못된 경우. 라우터에서 400으로 변환한다."""


def _validate_scores(scores: Mapping[str, int], moisture_source: str) -> None:
    """저장 전에 입력값을 검증한다. DB를 건드리기 전에 모두 걸러낸다."""
    if moisture_source not in MOISTURE_SOURCES:
        raise ScoringError(
            f"moisture_source는 {MOISTURE_SOURCES} 중 하나여야 합니다: {moisture_source}"
        )

    known_codes = {MOISTURE_CODE, *REQUIRED_METRIC_CODES}
    unknown = set(scores) - known_codes
    if unknown:
        raise ScoringError(f"알 수 없는 지표 코드입니다: {sorted(unknown)}")

    missing = [code for code in REQUIRED_METRIC_CODES if code not in scores]
    if missing:
        raise ScoringError(f"필수 지표 점수가 없습니다: {missing}")

    # 수분값 유무와 moisture_source가 어긋나면 데이터 신뢰도가 깨지므로 막는다.
    has_moisture = MOISTURE_CODE in scores
    if moisture_source == "none" and has_moisture:
        raise ScoringError("moisture_source가 none인데 수분 점수가 들어왔습니다")
    if moisture_source != "none" and not has_moisture:
        raise ScoringError(f"moisture_source가 {moisture_source}인데 수분 점수가 없습니다")

    for code, score in scores.items():
        # bool은 int의 하위 타입이라 별도로 걸러낸다
        if isinstance(score, bool) or not isinstance(score, int):
            raise ScoringError(f"{code} 점수는 정수여야 합니다: {score!r}")
        if not 0 <= score <= 100:
            raise ScoringError(f"{code} 점수는 0~100 범위여야 합니다: {score}")


def _load_metrics(db: Session, codes: set[str]) -> dict[str, SkinMetric]:
    """코드로 지표를 조회한다. 시드가 빠진 환경을 바로 알 수 있게 예외를 던진다."""
    metrics = db.scalars(select(SkinMetric).where(SkinMetric.code.in_(codes))).all()
    by_code = {m.code: m for m in metrics}

    missing = codes - set(by_code)
    if missing:
        raise ScoringError(
            f"지표 기준 데이터가 없습니다: {sorted(missing)} "
            "(scripts/seed_skin_metrics.py 실행 필요)"
        )
    return by_code


def _load_categories(db: Session, metric_ids: list[int]) -> dict[int, list[SkinMetricCategory]]:
    """지표별 구간을 한 번에 읽어 둔다 (지표마다 따로 조회하지 않기 위함)."""
    rows = db.scalars(
        select(SkinMetricCategory).where(SkinMetricCategory.metric_id.in_(metric_ids))
    ).all()

    by_metric: dict[int, list[SkinMetricCategory]] = {}
    for row in rows:
        by_metric.setdefault(row.metric_id, []).append(row)
    return by_metric


def find_category(categories: list[SkinMetricCategory], score: int) -> SkinMetricCategory:
    """점수가 속한 구간을 찾는다. 경계값에 구멍이 있으면 예외로 드러낸다."""
    for category in categories:
        if category.min_score <= score <= category.max_score:
            return category
    raise ScoringError(
        f"{score}점에 해당하는 판정 구간이 없습니다 (구간 경계값 설정을 확인하세요)"
    )


def label_and_save(
    db: Session,
    *,
    scores: Mapping[str, int],
    moisture_source: str,
    user_id: int | None = None,
    guest_id=None,
    image_id: int | None = None,
    logic_version: str = LOGIC_VERSION,
    expires_at: datetime | None = None,
) -> SkinAnalysis:
    """지표 점수를 라벨링해 분석 1건으로 저장한다.

    scores는 지표 코드 → 0~100 점수 (예: {"moisture": 72, "redness": 30, ...}).
    커밋은 호출하는 쪽(라우터)에서 한다.
    """
    _validate_scores(scores, moisture_source)

    metrics = _load_metrics(db, set(scores))
    categories_by_metric = _load_categories(db, [m.id for m in metrics.values()])

    analysis = SkinAnalysis(
        user_id=user_id,
        guest_id=guest_id,
        image_id=image_id,
        logic_version=logic_version,
        moisture_source=moisture_source,
        expires_at=expires_at,
    )

    for code, score in scores.items():
        metric = metrics[code]
        categories = categories_by_metric.get(metric.id, [])
        if not categories:
            raise ScoringError(
                f"'{metric.name}' 지표의 판정 구간이 없습니다 "
                "(scripts/seed_skin_metrics.py 실행 필요)"
            )

        # 점수와 함께 category_id도 저장해 둔다.
        # 이후 경계값이 바뀌어도 이 분석의 판정 결과는 그대로 남는다.
        category = find_category(categories, score)
        analysis.scores.append(
            SkinScore(metric_id=metric.id, category_id=category.id, score=score)
        )

    db.add(analysis)
    db.flush()
    return analysis
