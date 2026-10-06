import { useEffect, useRef, useState } from 'react'

const clamp = (value: number, max: number) => Math.max(-max, Math.min(max, value))

// 화면의 확대·이동만 담당한다. 분석에 전달하는 File은 변경하지 않는다.
export default function PhotoFrame({ file }: { file: File }) {
  const frame = useRef<HTMLDivElement>(null)
  const image = useRef<HTMLImageElement>(null)
  const drag = useRef<{ x: number; y: number; startX: number; startY: number } | null>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [natural, setNatural] = useState({ width: 0, height: 0 })
  const [zoom, setZoom] = useState(1)
  const [fit, setFit] = useState(false)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const url = URL.createObjectURL(file)
    if (image.current) image.current.src = url
    return () => URL.revokeObjectURL(url)
  }, [file])
  useEffect(() => {
    if (!frame.current) return
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }))
    observer.observe(frame.current)
    return () => observer.disconnect()
  }, [])

  const ratio = natural.width && natural.height
    ? (fit ? Math.min : Math.max)(size.width / natural.width, size.height / natural.height) * zoom : 0
  const width = natural.width * ratio, height = natural.height * ratio
  const maxX = Math.max(0, (width - size.width) / 2), maxY = Math.max(0, (height - size.height) / 2)
  const x = clamp(pan.x, maxX), y = clamp(pan.y, maxY)
  function reset(nextFit: boolean) { setFit(nextFit); setZoom(1); setPan({ x: 0, y: 0 }) }

  return <div className="large-photo">
    <div ref={frame} className="photo-frame" tabIndex={0} aria-label="사진 미리보기. 드래그하거나 방향키로 위치를 조절하세요."
      onPointerDown={event => {
        if (event.button !== 0) return
        event.currentTarget.focus({ preventScroll: true })
        event.currentTarget.setPointerCapture(event.pointerId)
        drag.current = { x, y, startX: event.clientX, startY: event.clientY }
      }}
      onPointerMove={event => {
        const start = drag.current
        if (start) setPan({ x: clamp(start.x + event.clientX - start.startX, maxX), y: clamp(start.y + event.clientY - start.startY, maxY) })
      }}
      onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }} onLostPointerCapture={() => { drag.current = null }}
      onKeyDown={event => {
        const move: Record<string, [number, number]> = { ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20] }
        const delta = move[event.key]
        if (delta) { event.preventDefault(); setPan({ x: clamp(x + delta[0], maxX), y: clamp(y + delta[1], maxY) }) }
      }}>
      <img ref={image} alt="분석할 얼굴 사진" draggable={false} onError={() => setFailed(true)}
        onLoad={event => { setNatural({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight }); setFailed(false) }}
        style={{ width: width || '100%', height: height || '100%', transform: `translate(-50%, -50%) translate(${x}px, ${y}px)` }} />
      {failed && <p className="photo-display-error" role="alert">사진을 표시할 수 없습니다. 다른 사진을 선택해 주세요.</p>}
    </div>
    <div className="photo-view-controls">
      <label>사진 확대 <input type="range" min={1} max={3} step={0.05} value={zoom} onChange={event => { setZoom(Number(event.target.value)); setPan({ x, y }) }} /><output>{zoom.toFixed(1)}배</output></label>
      <div className="actions"><button type="button" className="secondary" onClick={() => reset(!fit)}>{fit ? '프레임 채우기' : '사진 전체 보기'}</button><button type="button" className="text-button" onClick={() => reset(false)}>위치·확대 초기화</button></div>
      <p className="input-note">드래그하거나 방향키로 사진을 움직일 수 있어요. 확대·이동은 미리보기에만 적용되며 분석에는 원본 사진을 사용합니다.</p>
    </div>
  </div>
}
