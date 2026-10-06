import type { PreviewResponse, RuleExplanation } from '../api/cosmetics'

type Matches = PreviewResponse['recommendations'][number]['matches']

export function DailyCareDetails({ rules }: { rules: RuleExplanation[] }) {
  return <details className="match-details">
    <summary>일상 관리용으로 제안한 이유</summary>
    <p>기존 활성 보습 성분 규칙에 포함된 성분을 전성분표에서 확인했습니다. 수분 부족을 추정하거나 개선 지표 점수를 부여한 결과가 아닙니다.</p>
    <p>성분 함량·제형·개인 적합도는 확인되지 않았으며, 성분이 더 많다고 높은 순위를 부여하지 않습니다.</p>
    {rules.map(rule => <section key={rule.rule_code}>
      <h5>{rule.ingredient}</h5><p>{rule.evidence_summary}</p>
      <p><strong>근거의 적용 한계</strong><br />{rule.limitations}</p>
      <a href={rule.evidence_url} target="_blank" rel="noopener noreferrer">연결된 성분 근거 ↗</a>
    </section>)}
  </details>
}

export default function CosmeticMatchDetails({ matches }: { matches: Matches }) {
  const bases = new Map<string, Set<string>>()
  const unknowns = new Map<string, Set<string>>()
  const evidence = new Map<string, {
    url: string; summary: string; limitations: string
    ingredients: Set<string>; metrics: Set<string>
  }>()
  function collect(target: Map<string, Set<string>>, text: string, metric: string) {
    if (!target.has(text)) target.set(text, new Set())
    target.get(text)!.add(metric)
  }
  for (const match of matches) {
    if (match.interpretation) {
      collect(bases, match.interpretation.match_basis, match.metric_name)
      for (const item of match.interpretation.unverified_items) collect(unknowns, item, match.metric_name)
    }
    for (const rule of match.rule_details) {
      // 같은 URL이라도 요약/한계가 다르면 합치지 않는다.
      const key = JSON.stringify([rule.evidence_url, rule.evidence_summary, rule.limitations])
      if (!evidence.has(key)) evidence.set(key, {
        url: rule.evidence_url, summary: rule.evidence_summary, limitations: rule.limitations,
        ingredients: new Set(), metrics: new Set(),
      })
      evidence.get(key)!.ingredients.add(rule.ingredient)
      evidence.get(key)!.metrics.add(match.metric_name)
    }
  }
  const missingDetails = matches.filter(match => !match.interpretation).map(match => match.metric_name)
  const scope = (names: Set<string>) => names.size === matches.length ? '' : `${[...names].join(' · ')}: `

  return <details className="match-details">
    <summary>왜 매칭됐나요? — 근거·가정·미확인 정보</summary>
    {bases.size > 0 && <section>
      <h5>성분표에서 확인한 내용</h5>
      {[...bases].map(([text, names]) => <p key={text}>{scope(names)}{text}</p>)}
    </section>}
    <section>
      <h5>지표별 연결 가정 · 개발용</h5>
      {matches.map(match => <div key={match.metric_code}>
        <p><strong>{match.metric_name} · {match.ingredients.join(', ')}</strong><br />{match.interpretation?.metric_assumption}</p>
        {match.rule_details.map(rule => <p key={rule.rule_code}>{rule.ingredient}: {rule.rationale}</p>)}
      </div>)}
      {missingDetails.length > 0 && <p>{missingDetails.join(' · ')}: 상세 가정 정보가 없는 이전 API 응답입니다. 연구 근거가 개별 제품 효과를 보증하지는 않습니다.</p>}
    </section>
    {unknowns.size > 0 && <section>
      <h5>확인하지 못한 정보</h5>
      <ul>{[...unknowns].map(([text, names]) => <li key={text}>{scope(names)}{text}</li>)}</ul>
    </section>}
    {evidence.size > 0 && <details className="evidence-details">
      <summary>연결한 연구·안내 {evidence.size}건 보기</summary>
      {[...evidence].map(([key, item]) => <section key={key}>
        <h5>{[...item.ingredients].join(', ')} · {[...item.metrics].join(' · ')}</h5>
        <p>{item.summary}</p>
        <p><strong>적용 한계</strong><br />{item.limitations}</p>
        <a href={item.url} target="_blank" rel="noopener noreferrer">근거 ↗</a>
      </section>)}
    </details>}
  </details>
}
