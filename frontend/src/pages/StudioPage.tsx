import { useState } from 'react'
import { createHairRender, getHairRender, wait, type HairRender } from '../api/studio'
import PageIntro from '../components/PageIntro'
import Icon from '../components/Icon'
import { TaskStatus } from '../components/Shared'
import HairColorStudio from '../components/HairColorStudio'
import { useTask } from '../hooks/useTask'
import type { HairSessionResult } from '../types/sessionResults'

const POLL_MS = 2000
const POLL_LIMIT = 90 // 약 3분

export default function StudioPage({ hair, onUsed }: { hair: HairSessionResult | null; onUsed: () => void }) {
  const task = useTask()
  const recs = hair?.result.recommendations ?? []
  const [styleId, setStyleId] = useState(recs[0]?.style_id ?? '')
  const [render, setRender] = useState<HairRender | null>(null)

  if (!hair) return <section><PageIntro eyebrow="AI STUDIO" title="AI 헤어 스튜디오">추천받은 헤어스타일을 내 사진에 입혀 보고 머리색까지 바꿔볼 수 있어요.</PageIntro>
    <div className="studio-placeholder"><span className="feature-icon"><Icon name="sparkles" size={36} /></span><h3>먼저 헤어 추천을 받아 주세요</h3><p>얼굴형 분석에 쓴 정면 사진과 추천 스타일로 합성합니다.</p><a className="button" href="#/hair">얼굴형 · 헤어 추천 받기</a></div>
  </section>

  const selected = recs.find(item => item.style_id === styleId)
  function start() {
    if (task.busy || !hair || !selected) return
    setRender(null)
    void task.run(async signal => {
      let value = await createHairRender(hair.photo, selected.style_id, hair.result.run_id, signal)
      onUsed()
      for (let i = 0; value.status === 'pending'; i++) {
        if (i >= POLL_LIMIT) throw new Error('합성이 오래 걸리고 있어요. 잠시 후 다시 시도해 주세요.')
        await wait(POLL_MS, signal)
        value = await getHairRender(value.id, signal)
      }
      if (value.status === 'failed') throw new Error(value.error ?? '합성에 실패했습니다.')
      setRender(value)
    })
  }

  return <section><PageIntro eyebrow="AI STUDIO" title="AI 헤어 스튜디오">추천 스타일을 내 사진에 입혀 보고, 32가지 색으로 바로 바꿔 보세요.</PageIntro>
    <section className="form-card"><div className="card-heading"><span className="step-number">01</span><div><h3>입어볼 스타일</h3><p>얼굴형 분석 #{hair.analysis.id} · {hair.analysis.face_shape} 추천 결과</p></div></div>
      <fieldset className="studio-styles" disabled={task.busy}><legend className="sr-only">합성할 헤어스타일</legend>
        {recs.map(item => <label key={item.style_id} className={`studio-style${item.style_id === styleId ? ' selected' : ''}`}>
          <input type="radio" name="studio-style" value={item.style_id} checked={item.style_id === styleId} onChange={() => setStyleId(item.style_id)} />
          {item.image ? <img src={item.image} alt="" loading="lazy" /> : <span className="image-placeholder" />}
          <span><small>추천 {item.rank}</small>{item.name}</span>
        </label>)}
      </fieldset>
      <button className="recommend-button" type="button" disabled={task.busy || !selected} onClick={start}>{task.busy ? '합성하고 있어요…' : 'AI로 헤어 합성하기'}<Icon name="arrow" size={18} /></button>
      <p className="input-note">합성에는 30초 정도 걸려요. 비회원은 하루 이용 횟수가 정해져 있어요. 원본 사진은 저장하지 않아요.</p>
    </section>
    {task.busy && <div className="request-progress" role="status"><span className="spinner" /><div><strong>{selected?.name} 합성 중…</strong><p>얼굴은 그대로 두고 머리만 바꾸고 있어요.</p></div></div>}
    <TaskStatus busy={false} error={task.error} />
    {render && selected && <section className="form-card"><div className="card-heading"><span className="step-number">02</span><div><h3>머리색 바꿔보기</h3><p>{selected.name} · 색을 누르면 바로 바뀌어요.</p></div></div>
      <HairColorStudio render={render} styleName={selected.name} /></section>}
  </section>
}
