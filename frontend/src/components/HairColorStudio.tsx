import { useEffect, useMemo, useRef, useState } from 'react'
import { type HairRender, type HairRenderBase } from '../api/studio'
import { PALETTE, type HairBase, type HairColor } from '../studio/palette'
import { hexToRgb, loadPixels, prepareBase, renderColor, rgbToLab, type PreparedBase } from '../studio/recolor'

// 원래 머리색 칸의 베이스 기준 (palette.ts 기준과 같음)
const MID_MAX_L = 30
const BROWN_MAX_L = 52

async function prepare(base: HairRenderBase, size: readonly [number, number] | null, signal: AbortSignal) {
  const image = await loadPixels(base.image, size?.[0], size?.[1], signal)
  // 두 베이스·마스크를 같은 크기로 맞춤
  const mask = await loadPixels(base.mask, image.width, image.height, signal)
  return prepareBase(image, mask.data)
}

// 합성 결과 위에서 프리셋으로 머리색만 바꿔봄
export default function HairColorStudio({ render, styleName }: { render: HairRender; styleName: string }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const out = useRef<ImageData | null>(null)
  const [bases, setBases] = useState<Partial<Record<HairBase, PreparedBase>>>({})
  const [error, setError] = useState('')
  const [color, setColor] = useState<HairColor | null>(null)
  const [holding, setHolding] = useState(false)

  // 사진 속 원래 머리색 (원본 사진 대신 서버가 색만 저장)
  const original = useMemo<HairColor | null>(() => {
    if (!render.hair_hex) return null
    const [L] = rgbToLab(...hexToRgb(render.hair_hex))
    return { name: '원래 머리색', hex: render.hair_hex, base: L < MID_MAX_L ? 'mid' : L < BROWN_MAX_L ? 'brown' : 'light' }
  }, [render.hair_hex])

  useEffect(() => {
    if (!render.mid) return
    const controller = new AbortController()
    const { mid, brown, light } = render
    void (async () => {
      try {
        const midBase = await prepare(mid, null, controller.signal)
        const size = [midBase.width, midBase.height] as const
        // 이전 결과에는 brown 베이스가 없을 수 있음
        const [brownBase, lightBase] = await Promise.all([
          brown ? prepare(brown, size, controller.signal) : undefined,
          light ? prepare(light, size, controller.signal) : undefined,
        ])
        if (controller.signal.aborted) return
        out.current = new ImageData(...size)
        setBases({ mid: midBase, brown: brownBase, light: lightBase })
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : '합성 이미지를 불러오지 못했습니다.')
      }
    })()
    return () => controller.abort()
  }, [render])

  function pick(item: HairColor) {
    setColor(item)
  }

  // 중간 베이스가 없는 예전 결과는 밝은 베이스로
  const baseOf = (item: HairColor): HairBase => item.base === 'brown' && !render.brown ? 'light' : item.base
  const base = bases[color ? baseOf(color) : 'mid']
  useEffect(() => {
    const el = canvas.current, image = out.current
    if (!el || !base || !image) return
    el.width = image.width; el.height = image.height
    const ctx = el.getContext('2d')
    if (!ctx) return
    if (!color || holding) image.data.set(base.src)
    else renderColor(base, color, image.data)
    ctx.putImageData(image, 0, 0)
  }, [base, color, holding])

  function save() {
    const link = document.createElement('a')
    link.download = `boa-${styleName}-${color?.name ?? '기본'}.png`
    link.href = canvas.current?.toDataURL('image/png') ?? ''
    link.click()
  }

  const ready = Boolean(bases.mid)
  const swatch = (item: HairColor) => <button key={item.name} type="button" className="swatch" style={{ background: item.hex }} title={item.name}
    aria-label={item.name} aria-pressed={color?.name === item.name} onClick={() => pick(item)} />

  if (error) return <p role="alert" className="error-box">{error}</p>
  return <div className="color-studio">
    <div className="color-studio-stage">
      {!ready && <p role="status" className="color-studio-loading"><span className="spinner" />합성 이미지를 준비하고 있어요…</p>}
      <canvas ref={canvas} hidden={!ready} aria-label={`${styleName} 합성 결과${color ? ` · ${color.name}` : ''}`} />
      {ready && <div className="color-studio-actions">
        <button type="button" className="secondary" disabled={!color || !base}
          onPointerDown={() => setHolding(true)} onPointerUp={() => setHolding(false)} onPointerLeave={() => setHolding(false)} onPointerCancel={() => setHolding(false)}
          onKeyDown={e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); setHolding(true) } }} onKeyUp={() => setHolding(false)}>누르는 동안 염색 전 보기</button>
        <button type="button" disabled={!base} onClick={save}>이미지 저장</button>
      </div>}
    </div>
    <div className="color-studio-palette">
      <div className="color-studio-current"><span className="eyebrow">HAIR COLOR</span><strong>{color?.name ?? '기본 (어두운 갈색)'}</strong></div>
      {original && <fieldset className="swatch-group" disabled={!ready}>
        <legend>내 사진</legend>
        <div className="swatches">{swatch(original)}</div>
      </fieldset>}
      {PALETTE.map(group => <fieldset key={group.group} className="swatch-group" disabled={!ready}>
        <legend>{group.group}</legend>
        <div className="swatches">{group.colors.map(swatch)}</div>
      </fieldset>)}
      <button type="button" className="secondary" disabled={!color} onClick={() => setColor(null)}>기본 색으로</button>
    </div>
  </div>
}
