import { useState } from 'react'
import type { PreviewResponse } from '../api/cosmetics'
import Icon from './Icon'
import CosmeticMatchDetails, { DailyCareDetails } from './CosmeticMatchDetails'
import { cosmeticCategoryNames } from '../utils/cosmeticLabels'

const metricNames = { moisture: '수분', redness: '홍조', brightness: '밝기', trouble: '트러블', uniformity: '균일도' }

function ProductImage({ url, name }: { url: string | null; name: string }) {
  const [failed, setFailed] = useState(false)
  return url && !failed
    ? <img className="product-image" src={url} alt={name} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
    : <div className="product-image image-placeholder" aria-label="제품 이미지 없음"><span>boa.</span><small>제품 이미지 준비 중</small></div>
}

export default function CosmeticProductCard({ product, dailyCare, rednessCare = false, scorableTargetCount }: {
  product: PreviewResponse['recommendations'][number]
  dailyCare: boolean
  rednessCare?: boolean
  scorableTargetCount: number
}) {
  const prioritized = rednessCare && product.daily_care_rules?.some(rule => rule.ingredient === '판테놀')
  return <li className="product-card">
    <div className="product-visual"><span className="product-type">{cosmeticCategoryNames[product.category]}</span><ProductImage key={`${product.product_id}-${product.image_url}`} url={product.image_url} name={product.product_name} /></div>
    <div className="product-content"><p className="brand-name">{product.brand_name}</p><h4>{product.product_name}</h4>
      {dailyCare ? <p className="daily-care-badge">{prioritized ? '판테놀 함유 · 우선 표시' : rednessCare ? '보습 관리용' : '일상 관리용 · 개선 점수 없음'}</p>
        : <p className="match-score">{product.match_count}<span> / {scorableTargetCount}개 지표 성분 매칭</span></p>}
      <div className="ingredient-tags">{[...new Set(dailyCare ? product.daily_care_ingredients ?? [] : product.matches.flatMap(match => match.ingredients))].slice(0, 6).map(name => <span key={name}>{name}</span>)}</div>
      <p className="recommendation-reason">{product.recommendation_reason}</p>
      {!!Object.keys(product.product_name_claims ?? {}).length && <small className="product-note">제품명 표기(참고) · {Object.values(product.product_name_claims ?? {}).flat().join(', ')}</small>}
      {product.context_cautions?.map(caution => <small className="product-note" key={caution}>{caution}</small>)}
      {!!product.redness_care_ingredients?.length && !dailyCare && <small className="product-note">보습 보조 · 같은 조건에서 판테놀 함유 제품 우선</small>}
      {!!product.sensor_auxiliary_bonus && <small className="product-note">수분 지수 보조 반영 · 동점 후보 내 보습 성분: {product.sensor_auxiliary_ingredients?.join(', ')}</small>}

      {(product.shared_evidence_groups ?? []).length > 0 && <details className="shared-evidence"><summary>지표 간 공통 근거</summary>{product.shared_evidence_groups!.map(group => <p key={group.evidence_url}><strong>{group.metric_codes.map(code => metricNames[code]).join(' · ')}</strong><br />{group.explanation}</p>)}</details>}
      <div className="product-actions">{product.source_url && <a href={product.source_url} target="_blank" rel="noopener noreferrer">제품 정보 보기 <Icon name="arrow" size={16} /></a>}{product.bundle_suspected && <span>기획·세트 가능성</span>}</div>
      {dailyCare ? <DailyCareDetails rules={product.daily_care_rules ?? []} /> : <CosmeticMatchDetails matches={product.matches} />}
    </div>
  </li>
}
