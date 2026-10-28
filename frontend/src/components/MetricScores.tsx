import { scoreMaximum, levelDescription } from '../moisture/hydrationEstimate'
import type { AnalysisMetricScore } from '../api/cosmetics'
import { legacySkinIndex } from '../moisture/autoMeasurement'
const names = { moisture: '수분', redness: '홍조', brightness: '밝기', trouble: '트러블', uniformity: '균일도' }
const order = ['moisture', 'redness', 'brightness', 'trouble', 'uniformity'] as const
export default function MetricScores({ scores, moisture }: { scores: AnalysisMetricScore[]; moisture?: { score_max?: number; normalization_version?: string; moisture_level?: number; moisture_level_label?: string; estimated_state_label?: string; estimation_version?: string; resolution_limited?: boolean; algorithm_version?: string; relative_percent: number; baseline?: number; mean_count?: number; normalized_score?: number | null; used_for_scoring?: boolean; calibrated_score?: number | null; score_category?: string | null; experimental_index?: number | null; recommendation_eligible?: boolean; index_saturated?: boolean } | null }) {
  return <div className="score-grid">{order.map(code => {
    if (code === 'moisture' && moisture?.resolution_limited) return <div className="score-card unmeasured" key={code}><span>수분</span><strong>—</strong><span className="category-pill">확정 불가</span><small>기존 미세 반응 기록 · 추천 미반영</small></div>
    if(code === 'moisture' && moisture?.normalized_score != null && moisture.used_for_scoring) return <div className="score-card" key={code}><span>수분</span><strong>{moisture.normalized_score}<small>/ {scoreMaximum(moisture)}</small></strong><span className="category-pill">{moisture.moisture_level?levelDescription(moisture):moisture.estimated_state_label??moisture.score_category}</span><small>{moisture.estimation_version?'실험 추정 · 추천 반영':'이전 센서 점수 · 추천 반영'}</small></div>
    if (code === 'moisture' && moisture?.used_for_scoring) return <div className="score-card" key={code}><span>수분 · 보정 점수</span><strong>{moisture.calibrated_score}<small>/ 100</small></strong><span className="category-pill">{moisture.score_category}</span><small>센서 변화율 {moisture.relative_percent.toFixed(2)}% · 보정 모델 적용</small></div>
    if (code === 'moisture' && moisture) {
      const index = moisture.experimental_index ?? (moisture.baseline != null && moisture.mean_count != null
        ? legacySkinIndex(moisture.baseline, moisture.mean_count) : null)
      return <div className="score-card" key={code}><span>수분 · 센서 반응 지수</span><strong>{index == null ? '—' : index.toFixed(['skin-auto-v4','skin-auto-v5','skin-auto-v6'].includes(moisture.algorithm_version ?? '') ? 1 : 2)}<small>{index == null ? '' : '%'}</small></strong><span className="category-pill">측정 완료</span><small>{['skin-auto-v3','skin-auto-v4','skin-auto-v5','skin-auto-v6'].includes(moisture.algorithm_version ?? '') ? '접촉에 따른 정전용량 기여율' : moisture.experimental_index != null ? '이전 정전용량 실험 지수' : '이전 30-count 지수'} · 실제 피부 수분율 아님</small><small>{scores.some(s => s.metric_code === 'moisture') ? '추천에는 별도 입력 점수가 사용됨' : moisture.recommendation_eligible ? '추천 보조 반영 대상' : moisture.resolution_limited ? '분해능 제한 · 추천 반영 보류' : moisture.index_saturated ? '상한 도달 · 보조 반영 보류' : '저장·추천 연결 대기'}</small></div>
    }
    const score = scores.find(item => item.metric_code === code)
    if (!score) return <div className="score-card unmeasured" key={code}><span>{names[code]}</span><strong>—</strong><span className="category-pill">미측정</span><small>측정값이 없습니다</small></div>
    return <div className={`score-card${score.category_name === '개선 필요' ? ' needs-care' : ''}`} key={code}>
      <div className="score-card-top"><span>{score.metric_name}</span><span className="category-pill">{score.category_name}</span></div>
      <strong>{score.score}<small>/ 100</small></strong>
      <progress max={100} value={score.score} aria-label={`${score.metric_name} 원점수 ${score.score}`} />
      <small>{score.higher_is_better ? '높을수록 양호' : '낮을수록 양호'}</small>
    </div>
  })}</div>
}
