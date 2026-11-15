import { useEffect, useMemo, useRef, useState } from 'react'
import { type HairRender, type HairRenderBase } from '../api/studio'
import { PALETTE, type HairBase, type HairColor } from '../studio/palette'
import type { HairColorRecommendation } from '../studio/hairColorRecommendations'
import { hexToRgb, loadPixels, pickBase, prepareBase, renderColor, rgbToLab, type PreparedBase } from '../studio/recolor'

import { clampHairColor, hexToHsv, hsvToHex, type Hsv } from '../studio/hsv-input'

const INITIAL_HSV = hexToHsv('#3b2a20')

// base 필드 대체값 기준 (실제 베이스는 pickBase가 사진별 머리 밝기로 고름, 못 고를 때만 사용)
const MID_MAX_L = 30
const BROWN_MAX_L = 52

async function prepare(base: HairRenderBase, size: readonly [number, number] | null, signal: AbortSignal) {
  const image = await loadPixels(base.image, size?.[0], size?.[1], signal)
  // 두 베이스·마스크를 같은 크기로 맞춤
  const mask = await loadPixels(base.mask, image.width, image.height, signal, 'no-cache')
  return prepareBase(image, mask.data)
}

// 합성 결과 위에서 프리셋으로 머리색만 바꿔봄
// recommendedColors가 있으면 사용자가 고르기 전까지 첫 추천색을 입혀서 보여줌, basis: 추천 이유 한 줄
export default function HairColorStudio({ render, styleName, recommendedColors = [], basis }: {
  render: HairRender
  styleName: string
  recommendedColors?: HairColorRecommendation[]
  basis?: string
}) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const out = useRef<ImageData | null>(null)
  const [bases, setBases] = useState<Partial<Record<HairBase, PreparedBase>>>({})
  const [error, setError] = useState('')
  const [picked, setPicked] = useState<HairColor | null>(null)
  // 직접 고르거나 기본 색으로 되돌리기 전에는 첫 추천색
  const [touched, setTouched] = useState(false)
  const autoColor = touched ? null : recommendedColors[0]?.color ?? null
  const color = picked ?? autoColor
  const setColor = (item: HairColor | null) => { setTouched(true); setPicked(item) }
  const [holding, setHolding] = useState(false)
  const [hsv, setHsv] = useState<Hsv>(INITIAL_HSV)

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
    setHsv(hexToHsv(item.hex))
  }

  // 자동 추천색이 보이는 중이면 그 색에서 조절 시작
  const shownHsv = autoColor && !picked ? hexToHsv(autoColor.hex) : hsv
  function changeHsv(key: keyof Hsv, value: number) {
    const next = { ...shownHsv, [key]: value }
    const hex = clampHairColor(hsvToHex(next))
    const [L] = rgbToLab(...hexToRgb(hex))
    setHsv(next)
    setColor({ name: '직접 조절', hex, base: L < MID_MAX_L ? 'mid' : L < BROWN_MAX_L ? 'brown' : 'light' })
  }

  // 목표색 밝기에 가장 가까운 베이스 (사진마다 베이스 밝기가 다름), 못 고르면 지정 베이스·예전 결과는 밝은 베이스
  const baseOf = (item: HairColor): HairBase => (item.lockBase && bases[item.base] ? item.base : pickBase(bases, item.hex)) ?? (item.base === 'brown' && !render.brown ? 'light' : item.base)
  // 일부 베이스가 없는 예전 합성 결과에서도 색을 적용할 수 있게 (main 병합 시 합침)
  const base = color ? bases[baseOf(color)] ?? bases.brown ?? bases.light ?? bases.mid : bases.mid
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
      {recommendedColors.length > 0 && <fieldset className="swatch-group" disabled={!ready}>
        <legend>추천 헤어색</legend>
        {basis && <p className="color-studio-basis">{basis}</p>}
        <div className="swatches">{recommendedColors.map(({ color }) => swatch(color))}</div>
        {color && recommendedColors.find(item => item.color.name === color.name) && <p className="color-studio-basis">{recommendedColors.find(item => item.color.name === color.name)!.label}</p>}
      </fieldset>}
      <fieldset className="hair-hsv-input" disabled={!ready}>
        <legend>색상·채도·밝기 조절</legend>
        <label htmlFor="hair-input-h">색상 H <output>{Math.round(shownHsv.h)}°</output></label>
        <input id="hair-input-h" type="range" min="0" max="360" step="1" value={shownHsv.h} onChange={e => changeHsv('h', Number(e.target.value))} />
        <label htmlFor="hair-input-s">채도 S <output>{Math.round(shownHsv.s)}%</output></label>
        <input id="hair-input-s" type="range" min="0" max="100" step="1" value={shownHsv.s} onChange={e => changeHsv('s', Number(e.target.value))} />
        <label htmlFor="hair-input-v">밝기 V <output>{Math.round(shownHsv.v)}%</output></label>
        <input id="hair-input-v" type="range" min="0" max="100" step="1" value={shownHsv.v} onChange={e => changeHsv('v', Number(e.target.value))} />
        <div className="hair-hsv-preview"><span style={{ background: clampHairColor(hsvToHex(shownHsv)) }} /><span>{clampHairColor(hsvToHex(shownHsv)).toUpperCase()}</span></div>
      </fieldset>
      {original && <fieldset className="swatch-group" disabled={!ready}>
        <legend>내 사진</legend>
        <div className="swatches">{swatch(original)}</div>
      </fieldset>}
      <details><summary>프리셋에서 선택</summary>
      {PALETTE.map(group => <fieldset key={group.group} className="swatch-group" disabled={!ready}>
        <legend>{group.group}</legend>
        <div className="swatches">{group.colors.map(swatch)}</div>
      </fieldset>)}
      </details>
      <button type="button" className="secondary" disabled={!color} onClick={() => { setColor(null); setHsv(INITIAL_HSV) }}>기본 색으로</button>
    </div>
  </div>
}
