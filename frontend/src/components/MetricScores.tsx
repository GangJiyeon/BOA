import type { AnalysisMetricScore } from '../api/cosmetics'
const order = ['moisture', 'redness', 'brightness', 'trouble', 'uniformity'] as const
export default function MetricScores({ scores }: { scores: AnalysisMetricScore[] }) {
  return <div className="score-grid">{order.map(code => {
    const score = scores.find(item => item.metric_code === code)
    if (!score) return <div className="score-card unmeasured" key={code}><span>{code === 'moisture' ? '수분' : code}</span><strong>—</strong><span className="category-pill">미측정</span><small>측정값이 없습니다</small></div>
    return <div className={`score-card${score.category_name === '개선 필요' ? ' needs-care' : ''}`} key={code}>
      <div className="score-card-top"><span>{score.metric_name}</span><span className="category-pill">{score.category_name}</span></div>
      <strong>{score.score}<small>/ 100</small></strong>
      <progress max={100} value={score.score} aria-label={`${score.metric_name} 원점수 ${score.score}`} />
      <small>{score.higher_is_better ? '높을수록 양호' : '낮을수록 양호'}</small>
    </div>
  })}</div>
}
