import type { PreviewResponse } from '../api/cosmetics'
import Icon from './Icon'
import { SectionJump } from './Shared'

export default function CosmeticEmptyState({ result }: { result: PreviewResponse }) {
  const noTargets = result.target_count === 0
  const deferred = !noTargets && result.scorable_target_count === 0
  const noCatalog = result.stats.total_products === 0
  const dailyCare = result.recommendation_mode === 'daily_care'
  const title = noCatalog ? '추천할 제품 데이터가 아직 없습니다'
    : dailyCare ? '현재 조건에 맞는 일상 관리용 제품이 없습니다'
    : noTargets ? '현재 측정값에 개선 필요 지표가 없습니다'
    : deferred ? '분석은 완료됐지만 제품 매칭은 보류됐습니다'
    : '현재 추천 조건에 맞는 제품이 없습니다'
  const deferredNames = result.assessments.filter(item => result.deferred_metrics.includes(item.code)).map(item => item.name)
  return <div className="empty-box recommendation-empty">
    <Icon name="info" size={26} /><h4>{title}</h4>
    <p>{result.empty_reason || '추천 요청은 정상적으로 처리됐으며, 반환된 제품은 0개입니다.'}</p>
    {deferred && <p>매칭 보류 지표: <strong>{deferredNames.join(' · ')}</strong>. 점수는 표시하지만, 현재 추천 규칙에서 이 지표로 제품을 선정하지 않습니다.</p>}
    {result.missing_metrics.includes('moisture') && <p>수분은 미측정 상태입니다. 별도로 측정한 수분 점수가 있다면 입력에 추가할 수 있습니다.</p>}
    {(dailyCare || (!noTargets && !deferred)) && !noCatalog && <p>제품 종류와 직접 제외한 성분을 확인해 주세요. 조건에 따라 후보가 달라질 수 있습니다.</p>}
    <SectionJump targetId="skin-input-title">입력·추천 조건 확인</SectionJump>
  </div>
}
