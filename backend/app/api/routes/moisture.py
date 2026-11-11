"""Raw telemetry validation and persisted BOA skin moisture scores."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.session import get_db
from app.models.skin import SkinAnalysis
from app.schemas.moisture import MoistureReceipt, MoistureSubmission

router = APIRouter(prefix="/skin/moisture", tags=["skin"])


@router.post("/validate", response_model=MoistureReceipt)
def validate_measurement(body: MoistureSubmission, db: Session = Depends(get_db)):
    if body.measurement.source != "ble_sensor" and not get_settings().moisture_allow_simulation:
        raise HTTPException(403, "가상 측정 수신은 개발 설정에서만 허용됩니다")
    if body.analysis_id is not None and db.get(SkinAnalysis, body.analysis_id) is None:
        raise HTTPException(404, "연결할 피부 분석 결과가 없습니다")
    # This receipt associates an existing analysis ID only for this request.
    # It is not durable storage, ownership authorization, or a calibrated score.
    return MoistureReceipt(**body.model_dump(), server_received_at=datetime.now(timezone.utc))


from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.moisture import MoistureObservation
from app.schemas.moisture import CompletedReceipt, CompletedSubmission


from app.services.moisture import observation_receipt


@router.post('/results', response_model=CompletedReceipt)
def save_completed_measurement(body: CompletedSubmission, db: Session = Depends(get_db)):
    payload = body.result.model_dump(mode='json', exclude_none=True)
    key = str(body.result.measurement_id)
    def existing():
        row = db.scalar(select(MoistureObservation).where(MoistureObservation.measurement_id == key))
        if row is not None and (row.analysis_id != body.analysis_id or row.payload != payload):
            raise HTTPException(409, '같은 측정 ID를 다른 분석이나 다른 값에 재사용할 수 없습니다')
        return row
    prior = existing()
    if prior is not None:
        return observation_receipt(prior)
    analysis=db.scalar(select(SkinAnalysis).where(SkinAnalysis.id==body.analysis_id).with_for_update())
    if analysis is None:
        raise HTTPException(404, '연결할 피부 분석 결과가 없습니다')
    from app.services.cheek_calibration import convert
    from app.models.skin import SkinMetric
    summary = body.result.statistics()
    fixed=body.result.algorithm_version=='skin-fixed-3s-v1'
    if fixed:
        from app.services.moisture_normalization import normalize
        summary.update(normalize(body.result))
    else:
        summary.update(convert(body.result, summary['relative_percent']))
    # Historical engineering scores remain readable but cannot create a new
    # hydration category. New experimental states are inferred BEFORE scores.
    if summary['scoring_status'] in ('ready','experimental_estimate'):
        metric = db.scalar(select(SkinMetric).where(SkinMetric.code == 'moisture'))
        score=summary.get('normalized_score',summary.get('calibrated_score'))
        state_category = summary.get('estimation_category')
        categories = [] if metric is None else [c for c in metric.categories
            if (c.name == state_category if state_category else c.min_score <= score <= c.max_score)]
        if metric is None or not metric.higher_is_better or len(categories) != 1 or (not state_category and not categories[0].min_score <= score <= categories[0].max_score):
            if fixed:
                raise HTTPException(503,'수분 점수 카테고리 설정을 확인해 주세요.')
            summary.update(scoring_status='score_definition_invalid', calibrated_score=None)
        else:
            summary.update(used_for_scoring=True, score_category=categories[0].name, score_metric_name=metric.name)
            if fixed:
                from app.models.skin import SkinScore
                previous=db.scalar(select(SkinScore).where(SkinScore.analysis_id==analysis.id,SkinScore.metric_id==metric.id))
                if previous is None:
                    analysis.scores.append(SkinScore(metric=metric,category=categories[0],score=score))
                else:
                    previous.score=score;previous.category=categories[0]
                analysis.moisture_source='sensor'
    if body.result.algorithm_version in ('cheek-auto-v2', 'skin-auto-v3','skin-auto-v4','skin-auto-v5','skin-auto-v6'):
        from app.services.cheek_signal import signal_statistics
        summary.update(signal_statistics(body.result.baseline, [s.count for s in body.result.samples], modern=body.result.algorithm_version in ('skin-auto-v3','skin-auto-v4','skin-auto-v5','skin-auto-v6'), guarded=body.result.algorithm_version in ('skin-auto-v4','skin-auto-v5','skin-auto-v6'), stationary=body.result.algorithm_version == 'skin-auto-v6'))
        if body.result.algorithm_version in ('skin-auto-v3','skin-auto-v4','skin-auto-v5','skin-auto-v6'):
            summary['unit'] = 'capacitance_contact_fraction_percent'
        # Distinct from calibrated score: only eligible for experimental tie-breaking.
        summary['recommendation_eligible'] = not summary['index_saturated'] and not summary.get('used_for_scoring', False) and not summary.get('resolution_limited',False)
        if summary['recommendation_eligible']:
            summary['scoring_status'] = 'experimental_auxiliary'
        elif summary.get('resolution_limited'):
            summary['scoring_status'] = 'resolution_limited'
        elif summary['index_saturated']:
            summary['scoring_status'] = 'index_saturated'
    row = MoistureObservation(measurement_id=key, analysis_id=body.analysis_id,
                              payload=payload, summary=summary)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        prior = existing()
        if prior is not None:
            return observation_receipt(prior)
        raise HTTPException(409, '분석 상태가 변경되어 저장하지 못했습니다. 분석을 확인하세요.')
    db.refresh(row)
    return observation_receipt(row)
