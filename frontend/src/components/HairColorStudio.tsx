import { useEffect, useImperativeHandle, useMemo, useRef, useState, type Ref } from 'react'
import { type HairRender, type HairRenderBase } from '../api/studio'
import { PALETTE, type HairBase, type HairColor } from '../studio/palette'
import type { SkinToneResult } from '../api/skin'
import SkinToneSummary from './SkinToneSummary'
import type { HairColorRecommendation } from '../studio/hairColorRecommendations'
import { hexToRgb, loadPixels, prepareBase, renderColor, rgbToLab, type PreparedBase } from '../studio/recolor'

// 원래 머리색 항목의 base 메타데이터를 정하는 명도 기준
const MID_MAX_L = 30
const BROWN_MAX_L = 52

async function prepare(base: HairRenderBase, size: readonly [number, number] | null, signal: AbortSignal) {
  const image = await loadPixels(base.image, size?.[0], size?.[1], signal)
  // 두 베이스·마스크를 같은 크기로 맞춤
  const mask = await loadPixels(base.mask, image.width, image.height, signal, 'no-cache')
  return prepareBase(image, mask.data)
}

function paint(canvas: HTMLCanvasElement, image: ImageData, base: PreparedBase, color: HairColor | null) {
  if (canvas.width !== image.width) canvas.width = image.width
  if (canvas.height !== image.height) canvas.height = image.height
  const ctx = canvas.getContext('2d')
  if (!ctx) return false
  if (color) renderColor(base, color, image.data)
  else image.data.set(base.src)
  ctx.putImageData(image, 0, 0)
  return true
}

// 합성 결과 위에서 프리셋으로 머리색만 바꿔봄
// recommendedColors가 있으면 사용자가 고르기 전까지 첫 추천색을 입혀서 보여줌, basis: 추천 이유 한 줄
export default function HairColorStudio({ render, styleName, recommendedColors = [], basis, skinTone, onMakeup, makeupExport }: {
  render: HairRender
  styleName: string
  recommendedColors?: HairColorRecommendation[]
  skinTone?: SkinToneResult
  basis?: string
  onMakeup: (photo: File) => void
  makeupExport?: Ref<() => boolean>
}) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const out = useRef<ImageData | null>(null)
  const [bases, setBases] = useState<Partial<Record<HairBase, PreparedBase>>>({})
  const [error, setError] = useState('')
  const [exportError, setExportError] = useState('')
  const [exporting, setExporting] = useState(false)
  const exportPending = useRef(false)
  const [picked, setPicked] = useState<HairColor | null>(null)
  // 직접 고르거나 기본 색으로 되돌리기 전에는 첫 추천색
  const [touched, setTouched] = useState(false)
  const autoColor = touched ? null : recommendedColors[0]?.color ?? null
  const color = picked ?? autoColor
  const setColor = (item: HairColor | null) => { setTouched(true); setPicked(item) }
  const [holding, setHolding] = useState(false)

  // 사진 속 원래 머리색 (원본 사진 대신 서버가 색만 저장)
  const original = useMemo<HairColor | null>(() => {
    if (!render.hair_hex) return null
    const [L] = rgbToLab(...hexToRgb(render.hair_hex))
    return { name: '원래 머리색', hex: render.hair_hex, base: L < MID_MAX_L ? 'mid' : L < BROWN_MAX_L ? 'brown' : 'light' }
  }, [render.hair_hex])

  useEffect(() => {
    // brown을 우선하고 과거 결과는 light, mid 순으로 대체
    const pickBase: HairBase | null = render.brown ? 'brown' : render.light ? 'light' : render.mid ? 'mid' : null
    if (!pickBase) return
    const chosen = render[pickBase]!
    const controller = new AbortController()
    void (async () => {
      try {
        const prepared = await prepare(chosen, null, controller.signal)
        if (controller.signal.aborted) return
        out.current = new ImageData(prepared.width, prepared.height)
        setBases({ [pickBase]: prepared })
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : '합성 이미지를 불러오지 못했습니다.')
      }
    })()
    return () => controller.abort()
  }, [render])

  const pick = (item: HairColor) => setColor(item)

  // 모든 색상에 불러온 베이스 한 장을 사용
  const base = bases.brown ?? bases.light ?? bases.mid
  useEffect(() => {
    const el = canvas.current, image = out.current
    if (!el || !base || !image) return
    paint(el, image, base, holding ? null : color)
  }, [base, color, holding])

  function save() {
    const link = document.createElement('a')
    link.download = `boa-${styleName}-${color?.name ?? '기본'}.png`
    link.href = canvas.current?.toDataURL('image/png') ?? ''
    link.click()
  }

  useImperativeHandle(makeupExport, () => () => {
    if (!base || !canvas.current || !out.current) return false
    void openMakeup()
    return true
  })

  async function openMakeup() {
    const el = canvas.current, image = out.current
    if (!el || !image || !base || exportPending.current) return
    exportPending.current = true
    const from = window.location.hash
    setExportError('')
    setExporting(true)
    try {
      // 현재 선택한 머리색을 포함하고, 비교용으로 잠시 보이는 염색 전 이미지는 넘기지 않는다.
      if (!paint(el, image, base, color)) throw new Error()
      const blob = await new Promise<Blob>((resolve, reject) => {
        el.toBlob(result => result ? resolve(result) : reject(new Error()), 'image/png')
      })
      if (canvas.current === el && window.location.hash === from) onMakeup(new File([blob], `boa-ai-studio-${render.id}.png`, { type: blob.type }))
    } catch {
      if (canvas.current === el) setExportError('메이크업에 보낼 사진을 만들지 못했어요. 다시 시도해 주세요.')
    } finally {
      exportPending.current = false
      if (canvas.current === el) setExporting(false)
    }
  }

  const ready = Boolean(base)
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
        <button type="button" className="secondary" disabled={!base} onClick={save}>이미지 저장</button>
        <button type="button" disabled={!base || holding || exporting} onClick={() => void openMakeup()}>{exporting ? '사진 준비 중…' : '메이크업에 적용하기'}</button>
      </div>}
      {exportError && <p role="alert" className="error-box">{exportError}</p>}
    </div>
    <div className="color-studio-palette">
      <div className="color-studio-current"><span className="eyebrow">HAIR COLOR</span><strong>{color?.name ?? '기본 (중간 갈색)'}</strong></div>
      {recommendedColors.length > 0 && <fieldset className="swatch-group" disabled={!ready}>
        <legend>추천 헤어색</legend>
        {skinTone && <SkinToneSummary result={skinTone} recommendations={recommendedColors} basis={basis} source="ai-studio" />}
        {basis && <p className="color-studio-basis">{basis}</p>}
        <div className="swatches">{recommendedColors.map(({ color }) => swatch(color))}</div>
        {color && recommendedColors.find(item => item.color.name === color.name) && <p className="color-studio-basis">{recommendedColors.find(item => item.color.name === color.name)!.label}</p>}
      </fieldset>}
      {original && <fieldset className="swatch-group" disabled={!ready}>
        <legend>내 사진</legend>
        <div className="swatches">{swatch(original)}</div>
      </fieldset>}
      <details open><summary>프리셋에서 선택</summary>
      {PALETTE.map(group => <fieldset key={group.group} className="swatch-group" disabled={!ready}>
        <legend>{group.group}</legend>
        <div className="swatches">{group.colors.map(swatch)}</div>
      </fieldset>)}
      </details>
      <button type="button" className="secondary" disabled={!color} onClick={() => setColor(null)}>기본 색으로</button>
    </div>
  </div>
}
