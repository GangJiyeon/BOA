import { useEffect, useRef, useState } from 'react'
import type { HairRender } from '../api/studio'
import { PALETTE, type HairColor } from '../studio/palette'
import { loadPixels, prepareBase, renderColor, type PreparedBase } from '../studio/recolor'

// 합성 결과 위에서 40색 프리셋으로 머리색만 바꿔봄 (AI 추가 호출 없음)
export default function HairColorStudio({ render, styleName }: { render: HairRender; styleName: string }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const out = useRef<ImageData | null>(null)
  const [bases, setBases] = useState<Record<'light' | 'mid', PreparedBase> | null>(null)
  const [error, setError] = useState('')
  const [color, setColor] = useState<HairColor | null>(null)
  const [holding, setHolding] = useState(false)

  useEffect(() => {
    if (!render.light || !render.mid) return
    const controller = new AbortController()
    const { light, mid } = render
    void (async () => {
      try {
        const lightImage = await loadPixels(light.image, undefined, undefined, controller.signal)
        const size = [lightImage.width, lightImage.height] as const
        // 두 베이스·마스크를 같은 크기로 맞춤
        const [lightMask, midImage, midMask] = await Promise.all([
          loadPixels(light.mask, ...size, controller.signal),
          loadPixels(mid.image, ...size, controller.signal),
          loadPixels(mid.mask, ...size, controller.signal),
        ])
        if (controller.signal.aborted) return
        out.current = new ImageData(...size)
        setBases({ light: prepareBase(lightImage, lightMask.data), mid: prepareBase(midImage, midMask.data) })
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : '합성 이미지를 불러오지 못했습니다.')
      }
    })()
    return () => controller.abort()
  }, [render])

  useEffect(() => {
    const el = canvas.current, image = out.current
    if (!el || !bases || !image) return
    el.width = image.width; el.height = image.height
    const ctx = el.getContext('2d')
    if (!ctx) return
    const base = bases[color?.base ?? 'light']
    if (!color || holding) image.data.set(base.src)
    else renderColor(base, color, image.data)
    ctx.putImageData(image, 0, 0)
  }, [bases, color, holding])

  function save() {
    const link = document.createElement('a')
    link.download = `boa-${styleName}-${color?.name ?? '기본'}.png`
    link.href = canvas.current?.toDataURL('image/png') ?? ''
    link.click()
  }

  if (error) return <p role="alert" className="error-box">{error}</p>
  return <div className="color-studio">
    <div className="color-studio-stage">
      {!bases && <p role="status" className="color-studio-loading"><span className="spinner" />합성 이미지를 준비하고 있어요…</p>}
      <canvas ref={canvas} hidden={!bases} aria-label={`${styleName} 합성 결과${color ? ` · ${color.name}` : ''}`} />
      {bases && <div className="color-studio-actions">
        <button type="button" className="secondary" disabled={!color}
          onPointerDown={() => setHolding(true)} onPointerUp={() => setHolding(false)} onPointerLeave={() => setHolding(false)} onPointerCancel={() => setHolding(false)}
          onKeyDown={e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); setHolding(true) } }} onKeyUp={() => setHolding(false)}>누르는 동안 염색 전 보기</button>
        <button type="button" onClick={save}>이미지 저장</button>
      </div>}
    </div>
    <div className="color-studio-palette">
      <div className="color-studio-current"><span className="eyebrow">HAIR COLOR</span><strong>{color?.name ?? '기본 (애쉬 블론드)'}</strong></div>
      {PALETTE.map(group => <fieldset key={group.group} className="swatch-group" disabled={!bases}>
        <legend>{group.group}</legend>
        <div className="swatches">{group.colors.map(item =>
          <button key={item.name} type="button" className="swatch" style={{ background: item.hex }} title={item.name}
            aria-label={item.name} aria-pressed={color?.name === item.name} onClick={() => setColor(item)} />)}</div>
      </fieldset>)}
      <button type="button" className="secondary" disabled={!color} onClick={() => setColor(null)}>기본 색으로</button>
    </div>
  </div>
}
