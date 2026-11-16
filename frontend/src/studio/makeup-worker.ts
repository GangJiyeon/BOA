// 메이크업 계산 전용 워커: 얼굴 준비(수 초)·화장 렌더(수백 ms)를 화면 밖에서 (계산 중에도 슬라이더·버튼이 멈추지 않게)
// 같은 대상(key)의 렌더 요청이 밀리면 마지막 것만 그림 (슬라이더를 끌면 중간 값은 건너뜀)
import { lashLineMatch, lipPaleness, prepareFace, renderMakeup, type MakeupSettings, type PreparedFace, type ShapeFeatures } from './makeup'
import { browColor } from './brows'
import { lashColor } from './lashes'

export type WorkerImage = { width: number; height: number; data: Uint8ClampedArray }
export type FaceLiteMsg = Pick<PreparedFace, 'width' | 'height' | 'points' | 'upperLid' | 'lashStart'> & { lashRgb: ReturnType<typeof lashColor> }
export type WorkerRequest =
  | { type: 'prepare'; token: number; target: 'main' | 'preview'; image: WorkerImage; cleaned: Uint8ClampedArray; points: readonly (readonly number[])[]; features: ShapeFeatures | null }
  | { type: 'render'; key: string; target: 'main' | 'preview'; settings: MakeupSettings; browWeight: number; browFill?: { amount: number; hex: string } }
export type WorkerResponse =
  | { type: 'prepared'; token: number; target: 'main' | 'preview'; lite: FaceLiteMsg; eyeFit: number; lipPale: number; browHex: string }
  | { type: 'rendered'; key: string; token: number; width: number; height: number; data: Uint8ClampedArray }
  | { type: 'error'; token: number; message: string }

const faces: Partial<Record<'main' | 'preview', { token: number; face: PreparedFace; cleaned: Uint8ClampedArray }>> = {}
const pending = new Map<string, Extract<WorkerRequest, { type: 'render' }>>()
let scheduled = false

// 눈썹 교체: 원래 눈썹을 지운 사진(cleaned)을 weight만큼 섞은 얼굴 (brows.ts browReplacementFace와 같은 계산)
function withBrowBase(face: PreparedFace, cleaned: Uint8ClampedArray, weight: number): PreparedFace {
  if (weight <= 0 || cleaned.length !== face.src.length) return face
  if (weight >= 1) return { ...face, src: cleaned }
  const src = new Uint8ClampedArray(face.src.length)
  for (let i = 0; i < src.length; i++) src[i] = face.src[i] + (cleaned[i] - face.src[i]) * weight
  return { ...face, src }
}
function processNext() {
  scheduled = false
  // 큰 화면 먼저, 준비 안 된 대상은 다음으로
  const next = [...pending.values()].sort((a, b) => Number(b.target === 'main') - Number(a.target === 'main')).find(r => faces[r.target])
  if (!next) return
  pending.delete(next.key)
  const entry = faces[next.target]!
  const face = withBrowBase(entry.face, entry.cleaned, next.browWeight)
  const data = new Uint8ClampedArray(face.width * face.height * 4)
  renderMakeup(face, next.settings, data, next.browFill)
  const msg: WorkerResponse = { type: 'rendered', key: next.key, token: entry.token, width: face.width, height: face.height, data }
  ;(self as unknown as Worker).postMessage(msg, [data.buffer])
  schedule()
}
function schedule() {
  // setTimeout으로 양보해 그사이 들어온 새 요청이 pending을 덮어쓰게
  if (!scheduled && pending.size) { scheduled = true; setTimeout(processNext, 0) }
}

self.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const msg = event.data
  if (msg.type === 'render') { pending.set(msg.key, msg); schedule(); return }
  try {
    const face = prepareFace(msg.image, msg.points, msg.features)
    faces[msg.target] = { token: msg.token, face, cleaned: msg.cleaned }
    const lite: FaceLiteMsg = { width: face.width, height: face.height, points: face.points, upperLid: face.upperLid, lashStart: face.lashStart, lashRgb: lashColor(face) }
    const res: WorkerResponse = { type: 'prepared', token: msg.token, target: msg.target, lite, eyeFit: lashLineMatch(face), lipPale: lipPaleness(face), browHex: browColor(face) }
    ;(self as unknown as Worker).postMessage(res)
    schedule()
  } catch (err) {
    const res: WorkerResponse = { type: 'error', token: msg.token, message: err instanceof Error ? err.message : '얼굴을 준비하지 못했습니다.' }
    ;(self as unknown as Worker).postMessage(res)
  }
}
