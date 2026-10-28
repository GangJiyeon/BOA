"""Recommendation policy after a hydration category has been supplied.

No sensor-to-hydration thresholds, oiliness inference or formulation claims.
"""
VERSION='hydration-care-v1'
HUMECTANTS=frozenset({'글리세린','판테놀','하이알루로닉애씨드'})
LOSS_REDUCTION=frozenset({'다이메티콘','페트롤라툼'})


def describe(assessments,avoid_dryness):
    item=next((a for a in assessments if a.code=='moisture'),None)
    state='unmeasured' if item is None else {'개선 필요':'low','보통':'normal','양호':'sufficient'}.get(item.category,'unmeasured')
    return dict(version=VERSION,state=state,basis='supplied_moisture_category',
        strategy={'low':'보습 성분과 수분 손실 억제 성분을 우선합니다.',
                  'normal':'현재 보습 상태를 유지하며 다른 개선 지표를 함께 반영합니다.',
                  'sufficient':'추가 보습 가점 없이 다른 개선 지표를 우선합니다.',
                  'unmeasured':'수분 상태를 추정하지 않고 일반 관리 후보를 제안합니다.'}[state],
        dryness_exclusion_enabled=bool(state=='low' and avoid_dryness))
