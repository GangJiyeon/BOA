import { sensorMoistureCategory, type SensorMoistureInfo } from '../moisture/hydrationEstimate'
import type { AnalysisMetricScore } from '../api/cosmetics'
const names = { moisture: '수분', redness: '홍조', brightness: '밝기', trouble: '트러블', uniformity: '균일도' }
const order = ['moisture', 'redness', 'brightness', 'trouble', 'uniformity'] as const
type SensorMoistureDisplay = SensorMoistureInfo & {
  used_for_scoring?: boolean
  recommendation_eligible?: boolean
  index_saturated?: boolean
}
export default function MetricScores({ scores, moisture, manualMoisture }: { scores: AnalysisMetricScore[]; moisture?: SensorMoistureDisplay | null; manualMoisture?: string }) {
  return <div className="score-grid">{order.map(code => {
    const score = scores.find(item => item.metric_code === code)
    if (code === 'moisture' && manualMoisture && score) return <div className={`score-card${score.category_name === '개선 필요' ? ' needs-care' : ''}`} key={code}>
      <div className="score-card-top"><span>수분</span><span className="category-pill">{manualMoisture}</span></div>
      <strong>{score.category_name}</strong><small>직접 입력한 상태 · 추천에 반영</small>
    </div>
    if (code === 'moisture' && moisture) {
      const category = sensorMoistureCategory(moisture)
      const note = moisture.resolution_limited ? '측정 신호 부족 · 추천 미반영'
        : moisture.used_for_scoring ? '센서 측정 · 추천에 반영'
        : score ? '추천에는 별도 입력값을 사용했어요.'
        : moisture.recommendation_eligible ? '보습 추천에 보조 반영할 수 있어요.'
        : moisture.index_saturated ? '측정 범위 상한 도달 · 추천 미반영'
        : moisture.used_for_scoring === undefined ? '측정 결과 · 저장 확인 대기'
        : '측정 결과 · 추천 미반영'
      return <div className={`score-card${!category ? ' unmeasured' : category === '개선 필요' ? ' needs-care' : ''}`} key={code}>
        <div className="score-card-top"><span>수분</span><span className="category-pill">측정기</span></div>
        <strong>{category ?? '판정 불가'}</strong><small>{note}</small>
      </div>
    }
    if (!score) return <div className="score-card unmeasured" key={code}><span>{names[code]}</span><strong>—</strong><span className="category-pill">미측정</span><small>측정값이 없습니다</small></div>
    // 밝기: 원래 피부색·촬영 노출이 함께 반영되는 값이라 피부 상태(양호/개선 필요) 판정 대신 참고 정보로만 표시
    if (code === 'brightness') return <div className="score-card" key={code}>
      <div className="score-card-top"><span>{score.metric_name}</span><span className="category-pill">참고</span></div>
      <strong>{score.score}<small>/ 100</small></strong>
      <progress max={100} value={score.score} aria-label={`${score.metric_name} 참고 점수 ${score.score}`} />
      <small>원래 피부색·조명에 따라 달라지는 값 · 상태 판정 아님</small>
    </div>
    return <div className={`score-card${score.category_name === '개선 필요' ? ' needs-care' : ''}`} key={code}>
      <div className="score-card-top"><span>{score.metric_name}</span><span className="category-pill">{score.category_name}</span></div>
      <strong>{score.score}<small>/ 100</small></strong>
      <progress max={100} value={score.score} aria-label={`${score.metric_name} 원점수 ${score.score}`} />
      <small>{score.higher_is_better ? '높을수록 양호' : '낮을수록 양호'}</small>
    </div>
  })}</div>
}
