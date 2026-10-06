import { useState } from 'react'
import type { PreviewResponse } from '../api/cosmetics'
import CosmeticMatchDetails, { DailyCareDetails } from './CosmeticMatchDetails'
import { cosmeticCategoryNames } from '../utils/cosmeticLabels'

const metricNames = { moisture: '수분', redness: '홍조', brightness: '밝기', trouble: '트러블', uniformity: '균일도' }

function ProductImage({ url, name }: { url: string | null; name: string }) {
  const [failed, setFailed] = useState(false)
  return url && !failed
    ? <img className="product-image" src={url} alt={name} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
    : <div className="product-image image-placeholder" aria-label="제품 이미지 없음">BOA</div>
}

export default function CosmeticProductCard({ product, dailyCare, scorableTargetCount }: {
  product: PreviewResponse['recommendations'][number]
  dailyCare: boolean
  scorableTargetCount: number
}) {
  return <li className="product-card">
    <ProductImage key={`${product.product_id}-${product.image_url}`} url={product.image_url} name={product.product_name} />
    <div className="product-content"><p className="brand-name">{product.brand_name} · {cosmeticCategoryNames[product.category]}</p><h4>{product.product_name}</h4>
      {dailyCare ? <p className="daily-care-badge">일상 관리용 · 개선 점수 없음</p>
        : <p className="match-score">{product.match_count}<span> / {scorableTargetCount}개 지표 성분 매칭</span></p>}
      <div className="ingredient-tags">{[...new Set(dailyCare ? product.daily_care_ingredients ?? [] : product.matches.flatMap(match => match.ingredients))].slice(0, 6).map(name => <span key={name}>{name}</span>)}</div>
      <p className="recommendation-reason">{product.recommendation_reason}</p>
      <p className="input-note">성분이 포함된 후보 제품이며, 제품 효과를 보증하지 않습니다.</p>
      {(product.shared_evidence_groups ?? []).map(group => <p key={group.evidence_url}>
        <strong>{group.metric_codes.map(code => metricNames[code]).join(' · ')}: 근거 공유</strong><br />{group.explanation}
      </p>)}
      <div className="product-actions">{product.source_url && <a href={product.source_url} target="_blank" rel="noopener noreferrer">제품 정보 보기 ↗</a>}{product.bundle_suspected && <span>기획·세트 가능성</span>}</div>
      {dailyCare ? <DailyCareDetails rules={product.daily_care_rules ?? []} /> : <CosmeticMatchDetails matches={product.matches} />}
    </div>
  </li>
}
