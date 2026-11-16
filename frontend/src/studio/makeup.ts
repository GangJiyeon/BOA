import type { FaceFit } from './face-fit'
import type { FaceShape } from './makeup-looks'
// 사진 한 장에 쉐딩·하이라이터·블러셔·립을 입힘 (AI 호출 없음)
// 위치: MediaPipe 얼굴 랜드마크(478점, 0~1 좌표)로 부위별 마스크를 만듦 → 사진마다 한 번만 계산
// 색: HSV에서 색상·채도만 바꾸고 명도(V)는 원본 유지 → 피부결·입술 주름이 남음
// 형태별 마스크를 사진당 한 번 계산. 색·농도·형태 선택 시 브라우저에서 즉시 합성.

export type Pt = readonly [number, number]
// glow: 블러셔 전용 광(0~1). 광대 윗부분의 원래 밝은 피부에만 블러셔 색이 섞인 광을 얹는다.
// glow: 블러셔 광, tip: 블러셔에 코끝 더하기(0~1), shimmer: 아이섀도 눈두덩 펄(0~1), soft: 립 경계 흐리게
// beard: 피부 보정에서 수염 자국 가리기(0~1, 남성), gloss: 립 모양과 따로 넣는 은은한 광(0~1), cleft: 턱끝 가운데 세로 음영(엉덩이턱, 0~1), noseCleft: 코끝 가운데 세로 음영(엉덩이코, 0~1)
export type MakeupLayer = { on: boolean; hex: string; amount: number; glow?: number; tip?: number; shimmer?: number; soft?: boolean; beard?: number; gloss?: number; cleft?: number; noseCleft?: number }
// 섀도 3층: eyeshadow(눈두덩 기본색)·shadowPoint(눈꼬리·쌍꺼풀 진한 색)·underShadow(아래 눈가)
// aegyo: 애교살 (애교살 영역에 섀도, 아래 주름에 옅은 음영 선)
// skin: 쿠션 피부 보정 (결 정리·붉은기 완화·쿠션 색 쪽으로 톤 맞춤), hex = 쿠션 색
export type MakeupPart = 'skin' | 'shading' | 'noseShading' | 'highlight' | 'blush' | 'eyeshadow' | 'shadowPoint' | 'underShadow' | 'aegyo' | 'eyeliner' | 'lip'
export type MakeupShapes = {
  skin: 'cushion'
  shading: 'natural' | 'vline' | 'chin' | 'sculpt'
  noseShading: 'soft' | 'slim' | 'tip' | 'sculpted' | 'vtip' | 'wings'
  highlight: 'standard' | 'center' | 'cheek' | 'cheekNose' | 'cheekChin' | 'tzone' | 'bone'
  blush: 'round' | 'wide' | 'diagonal' | 'undereye' | 'hangover' | 'teary' | 'sunburn' | 'slim' | 'ennui' | 'midface'
  eyeshadow: 'basic' | 'wing' | 'smoky' | 'long'
  shadowPoint: 'wing' | 'long' | 'smoky'
  underShadow: 'outer' | 'full' | 'wide'
  aegyo: 'soft' | 'long'
  eyeliner: 'basic' | 'wing' | 'down' | 'longWing' | 'longDown'
  lip: 'glossy' | 'gradient' | 'blur'
}
export type MakeupSettings = { [P in MakeupPart]: MakeupLayer & { shape: MakeupShapes[P] } }
export const MAKEUP_SHAPES: { [P in MakeupPart]: { id: MakeupShapes[P]; label: string; description: string }[] } = {
  skin: [{ id: 'cushion', label: '쿠션', description: '결 정리·붉은기 완화·쿠션 색 쪽으로 톤 맞춤' }],
  shading: [
    { id: 'natural', label: '자연스러운 턱선', description: '양옆 턱선을 부드럽게' },
    { id: 'vline', label: 'V라인', description: '아래 턱선을 길게 연결' },
    { id: 'chin', label: '턱끝 중심', description: '턱끝 양옆을 작게 정돈' },
    { id: 'sculpt', label: '골격', description: '광대 밑을 사선으로 눌러 광대·턱 골격이 보이게' },
  ],
  noseShading: [{ id: 'sculpted', label: '조각 코끝', description: '코끝 양옆과 아래를 분리해 입체적으로' }, { id: 'vtip', label: '코끝 옆면', description: '실제 코끝 어깨와 콧볼 위쪽 경계를 따라 정돈' }, { id: 'wings', label: '콧볼 정돈', description: '콧대는 비우고 콧볼 바깥만 작게' }, { id: 'soft', label: '부드러운 콧대', description: '코 양옆의 은은한 음영' }, { id: 'slim', label: '또렷한 콧대', description: '검출된 콧대 옆면을 따라 가늘고 부드럽게' }, { id: 'tip', label: '코끝 정돈', description: '콧구멍 아래는 비우고 코끝 양옆을 부드럽게 정돈' }],
  highlight: [
    { id: 'bone', label: '골격 강조', description: '광대 윗면과 턱선을 작게 밝혀 골격을 강조, 넓은 광대·사각턱은 약하게' },
    { id: 'standard', label: '균형', description: '광대와 얼굴 중앙' },
    { id: 'center', label: '중앙', description: '콧대와 턱끝 중심' },
    { id: 'cheek', label: '광대', description: '광대 위쪽 중심' },
    { id: 'cheekNose', label: '광대·코끝', description: '광대 위쪽과 코끝' },
    { id: 'cheekChin', label: '광대·턱끝', description: '광대 위쪽과 턱끝' },
    { id: 'tzone', label: 'T존', description: '이마 가운데·가는 콧대·턱끝 (남성)' },
  ],
  blush: [
    { id: 'round', label: '볼 중앙', description: '볼 중앙의 작은 원형 발색' },
    { id: 'wide', label: '넓고 옅게', description: '볼 전체에 넓게 퍼지는 부드러운 발색' },
    { id: 'diagonal', label: '사선 광대', description: '광대 따라 바깥쪽으로' },
    { id: 'undereye', label: '눈 밑 가로', description: '눈 아래에 길고 얇게' },
    { id: 'hangover', label: '숙취', description: '눈 밑을 넓게 물들이고 콧등까지 가로로 연결' },
    { id: 'teary', label: '울먹', description: '언더 라인 바로 아래와 코끝을 붉게' },
    { id: 'sunburn', label: '선번', description: '광대 위에서 콧등을 가로질러 햇볕에 탄 듯' },
    { id: 'slim', label: '슬림 사선', description: '관자놀이에서 광대 바깥을 타고 내려와 얼굴이 갸름해 보이게' },
    { id: 'ennui', label: '나른한', description: '눈꼬리를 C자로 감싸고 코끝·턱끝에 살짝' },
    { id: 'midface', label: '중안부 짧게', description: '볼 중앙을 조금 높고 안쪽에, 코끝까지 이어 중안부가 짧아 보이게' },
  ],
  eyeshadow: [
    { id: 'basic', label: '소프트 음영', description: '속눈썹 가까이에서 위로 자연스럽게 소실되는 음영' },
    { id: 'wing', label: '눈꼬리 음영', description: '안쪽은 비우고 바깥 1/3에 가로로 깊이를 더해요' },
    { id: 'smoky', label: '스머지 음영', description: '속눈썹 주변과 언더 바깥쪽에 부드러운 번짐' },
    { id: 'long', label: '꼬리 길게', description: '눈꼬리 뒤로 길게 빼고 언더 바깥쪽과 이어요' },
  ],
  shadowPoint: [
    { id: 'wing', label: '눈꼬리', description: '바깥 1/3에 진한 색' },
    { id: 'long', label: '꼬리 길게', description: '눈꼬리 뒤로 길게' },
    { id: 'smoky', label: '스머지', description: '속눈썹 가까이 번지게' },
  ],
  underShadow: [
    { id: 'outer', label: '바깥쪽', description: '아래 눈가 바깥 절반' },
    { id: 'full', label: '전체', description: '아래 눈가 전체를 옅게' },
    { id: 'wide', label: '넓게', description: '아래 눈가를 넓고 옅게 (도치)' },
  ],
  aegyo: [{ id: 'soft', label: '애교살', description: '애교살에 섀도를 칠하고 아래 주름에 옅은 음영으로 볼록하게' }, { id: 'long', label: '긴 애교살', description: '눈꼬리 쪽까지 길게 이어 칠함 (도치)' }],
  eyeliner: [
    { id: 'basic', label: '기본 라인', description: '꼬리 없이 윗속눈썹을 따라 채워요' },
    { id: 'wing', label: '짧은 일자 꼬리', description: '기본 라인에서 가로로 짧게 이어요' },
    { id: 'down', label: '살짝 내린 꼬리', description: '눈 바깥쪽을 짧고 완만하게 내려요' },
    { id: 'longWing', label: '긴 꼬리', description: '기본 라인에서 가로로 길게 빼요' },
    { id: 'longDown', label: '긴 내린 꼬리', description: '눈 바깥쪽을 조금 길게 완만히 내려요' },
  ],
  lip: [
    { id: 'blur', label: '블러립', description: '입술 경계는 흐리게, 안쪽은 부드럽게 채워요' },
    { id: 'glossy', label: '촉촉립', description: '투명한 색과 부드러운 광택' },
    { id: 'gradient', label: '그라데이션립', description: '입술 안쪽부터 물들듯' },
  ],
}
export type BrowRegion = { x: number; y: number; width: number; height: number; angle: number }
// 화면 쪽(눈썹·속눈썹 그리기)에 필요한 얼굴 정보만 (전체 마스크는 워커에 둠)
export type FaceLite = Pick<PreparedFace, 'width' | 'height' | 'points' | 'upperLid' | 'lashStart' | 'browRegions'> & { lashRgb?: ReturnType<typeof import('./lashes').lashColor> }
export type PreparedFace = {
  browRegions?: Partial<Record<'left' | 'right', BrowRegion>>
  width: number
  height: number
  src: Uint8ClampedArray
  points: readonly Pt[]
  variants: { [P in MakeupPart]: Record<MakeupShapes[P], Float32Array> }
  lipGloss: Float32Array
  lipMeanV: number
  lipSpecular: Float32Array
  lipShine: number
  // 입술 안에서 주변보다 밝은 정도(0~1, .5가 평균) → 글로시 광이 굴곡을 따라 맺히게
  lipRel: Float32Array
  // 코끝 블러셔·눈두덩 펄 자리
  blushNose: Float32Array
  lidShine: Float32Array
  aegyoShadow: Record<MakeupShapes['aegyo'], Float32Array>
  // 사진 속 속눈썹 라인에 맞춘 윗눈꺼풀 점 (랜드마크 번호 → 좌표)
  upperLid: Record<number, Pt>
  // 속눈썹 시작점: 눈머리에서 흰자가 보이기 시작하는 곳 (눈 길이 비율, 몽고주름에 덮인 부분 제외)
  lashStart: { left: number; right: number }
  // 피부 트러블: 주변보다 어둡거나 붉은 작은 점(0~1)과 그 자리를 메울 주변 피부색(RGB)
  // 수염 자국: 입 주변·턱에서 볼 피부보다 어둡고 푸르스름한 정도(0~1)와 볼 피부 Lab
  beardMask: Float32Array
  beardRef: [number, number, number]
  // 내 눈썹 빈 곳 (0~1, 에셋 없이 채울 자리)
  browFill: Float32Array
  spotMask: Float32Array
  // 엉덩이턱·엉덩이코 음영 자리, 엉덩이코 하이라이트 자리
  chinCleft: Float32Array
  chinCleftHL: Float32Array
  // 코·광대 분석 층 (음영·하이라이트)
  featShade: Float32Array
  featHL: Float32Array
  noseCorrection: Float32Array
  noseFit: boolean  // 코 맞춤 기법을 그렸는지 (분석 있음)
  noseAccent: Float32Array
  nosePalette: NosePalette
  noseCleft: Float32Array
  noseCleftHL: Float32Array
  // 턱 쉐딩을 넓게 한 번 더 흐린 마스크 (경계가 띠처럼 보이지 않게)
  shadingSoft: Record<MakeupShapes['shading'], Float32Array>
  spotFill: Uint8ClampedArray
  // 피부 보정용: 피부 마스크(눈·눈썹·입술 제외), 결 정리한 사진, 넓게 흐린 a·b(얼룩), 피부 평균 Lab
  skinMask: Float32Array
  skinSmooth: Uint8ClampedArray
  // 볼 집중 보정 자리 (0~1)
  skinCheek: Float32Array
  skinLowA: Float32Array
  skinLowB: Float32Array
  skinMean: [number, number, number]
  cheekGlow: Float32Array
}

const FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
const LIPS_OUTER = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146]
const LIPS_INNER = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95]
const LEFT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
const RIGHT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
// 좌우 대칭 점 (사진 왼쪽, 오른쪽)
const SIDES = [
  { apple: 50, outer: 123, under: 117, upper: 116, temple: 127, temple2: 162, jaw: [234, 93, 132, 58, 172] },
  { apple: 280, outer: 352, under: 346, upper: 345, temple: 356, temple2: 389, jaw: [454, 323, 361, 288, 397] },
]

export const DEFAULT_MAKEUP: MakeupSettings = {
  skin: { on: false, hex: '#e8c2a8', amount: 0, shape: 'cushion' },
  shading: { on: true, hex: '#a3826a', amount: 0.5, shape: 'natural' },
  noseShading: { on: false, hex: '#a3826a', amount: 0.3, shape: 'soft' },
  highlight: { on: true, hex: '#fff3e6', amount: 0.5, shape: 'standard' },
  blush: { on: true, hex: '#f08a80', amount: 0.5, shape: 'round' },
  eyeshadow: { on: true, hex: '#99877d', amount: 0.4, shape: 'basic' },
  shadowPoint: { on: false, hex: '#7a6558', amount: 0, shape: 'wing' },
  underShadow: { on: false, hex: '#b08a88', amount: 0, shape: 'outer' },
  aegyo: { on: false, hex: '#fbe8e2', amount: 0, shape: 'soft' },
  eyeliner: { on: true, hex: '#80624f', amount: 0.65, shape: 'basic' },
  lip: { on: true, hex: '#c2414b', amount: 0.7, shape: 'gradient' },
}

export function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16)
  return [n >> 16 & 255, n >> 8 & 255, n & 255]
}

// r,g,b 0~255 → h 0~360, s·v 0~1
export function rgbToHsv(r: number, g: number, b: number): [number, number, number] {
  r /= 255; g /= 255; b /= 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min
  let h = 0
  if (d > 0) {
    if (max === r) h = 60 * (((g - b) / d) % 6)
    else if (max === g) h = 60 * ((b - r) / d + 2)
    else h = 60 * ((r - g) / d + 4)
  }
  return [h < 0 ? h + 360 : h, max ? d / max : 0, max]
}

function hsvToRgb(h: number, s: number, v: number, out: number[]) {
  const c = v * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = v - c
  const k = Math.floor(h / 60) % 6
  const [r, g, b] = k === 0 ? [c, x, 0] : k === 1 ? [x, c, 0] : k === 2 ? [0, c, x] : k === 3 ? [0, x, c] : k === 4 ? [x, 0, c] : [c, 0, x]
  out[0] = (r + m) * 255; out[1] = (g + m) * 255; out[2] = (b + m) * 255
}

// sRGB(0~255) ↔ Lab (피부 보정용)
// 속도: 0~255 정수 입력은 표, 선형→sRGB는 4096칸 표 + 선형 보간 (Math.pow가 렌더 시간의 큰 몫)
const srgbLinExact = (c: number) => { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4) }
const linSrgbExact = (v: number) => 255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - 0.055)
const SRGB_LIN = Float64Array.from({ length: 256 }, (_, i) => srgbLinExact(i))
const LIN_STEPS = 4096, LIN_SRGB = Float64Array.from({ length: LIN_STEPS + 2 }, (_, i) => linSrgbExact(Math.min(1, i / LIN_STEPS)))
const srgbLin = (c: number) => (c | 0) === c && c >= 0 && c <= 255 ? SRGB_LIN[c] : srgbLinExact(c)
const linSrgb = (v: number) => {
  if (!(v > 0) || v >= 1) return linSrgbExact(v)
  const f = v * LIN_STEPS, i = f | 0
  return LIN_SRGB[i] + (LIN_SRGB[i + 1] - LIN_SRGB[i]) * (f - i)
}
const fLab = (t: number) => t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116
const fInv = (t: number) => { const t3 = t * t * t; return t3 > 0.008856 ? t3 : (t - 16 / 116) / 7.787 }
function toLab(r: number, g: number, b: number): [number, number, number] {
  const R = srgbLin(r), G = srgbLin(g), B = srgbLin(b)
  const x = fLab((0.4124564 * R + 0.3575761 * G + 0.1804375 * B) / 0.95047), y = fLab(0.2126729 * R + 0.7151522 * G + 0.072175 * B), z = fLab((0.0193339 * R + 0.119192 * G + 0.9503041 * B) / 1.08883)
  return [116 * y - 16, 500 * (x - y), 200 * (y - z)]
}
function fromLab(L: number, a: number, b: number, out: number[]) {
  const fy = (L + 16) / 116, X = 0.95047 * fInv(fy + a / 500), Y = fInv(fy), Z = 1.08883 * fInv(fy - b / 200)
  out[0] = linSrgb(3.2404542 * X - 1.5371385 * Y - 0.4985314 * Z); out[1] = linSrgb(-0.969266 * X + 1.8760108 * Y + 0.041556 * Z); out[2] = linSrgb(0.0556434 * X - 0.2040259 * Y + 1.0572252 * Z)
}
export function labToHex(L: number, a: number, b: number) {
  const o = [0, 0, 0]
  fromLab(L, a, b, o)
  return '#' + o.map(v => Math.round(Math.min(255, Math.max(0, v))).toString(16).padStart(2, '0')).join('')
}
export type NosePalette = { skin: [number,number,number]; shadow: [number,number,number]; depth: number; chroma: [number,number]; samples: number }
// 코의 밝은 피부와 옆면의 기존 그림자에서 Lab 차이를 추출한다. 콧구멍·반사광·붉은 점은 제외.
export function sampleNosePalette(image: {width:number;height:number;data:Uint8ClampedArray},points:readonly Pt[]): NosePalette {
  const {width:w,height:h,data}=image
  const noseW=dist(points[129],points[358]),radius=Math.max(1,Math.round(noseW*.035))
  const sample=(ids:number[])=>{
    const pixels=new Set<number>(),colors:[number,number,number][]=[]
    for(const id of ids){
      const [cx,cy]=points[id]
      for(let dy=-radius;dy<=radius;dy++)for(let dx=-radius;dx<=radius;dx++){
        if(dx*dx+dy*dy>radius*radius)continue
        const x=Math.round(cx)+dx,y=Math.round(cy)+dy
        if(x<0||y<0||x>=w||y>=h)continue
        const i=y*w+x
        if(pixels.has(i)||data[i*4+3]===0)continue
        pixels.add(i);colors.push(toLab(data[i*4],data[i*4+1],data[i*4+2]))
      }
    }
    return colors
  }
  const median=(values:number[])=>{const sorted=[...values].sort((a,b)=>a-b),mid=Math.floor(sorted.length/2);return sorted.length%2?sorted[mid]:(sorted[mid-1]+sorted[mid])/2}
  const middle=(samples:[number,number,number][]):[number,number,number]=>[0,1,2].map(c=>median(samples.map(v=>v[c]))) as [number,number,number]
  const lit=sample([6,197,195,5,4])
  // 투명·범위 밖인 입력에는 고정 피부색을 넣지 않는다.
  if(!lit.length)return {skin:[0,0,0],shadow:[0,0,0],depth:0,chroma:[0,0],samples:0}
  const skin=middle(lit)
  const sides=sample([122,351,196,419,3,248,51,281,45,275,49,279,48,278])
  const clean=sides.filter(([L,a,b])=>L>Math.max(8,skin[0]*.58)&&L<skin[0]-1&&Math.abs(a-skin[1])<10&&Math.abs(b-skin[2])<12)
  const shadow=clean.length>=5?middle(clean):[...skin] as [number,number,number]
  const clamp=(v:number,lo:number,hi:number)=>Math.max(lo,Math.min(hi,v))
  return {skin,shadow,depth:clamp(skin[0]-shadow[0],4,12),chroma:[clamp(shadow[1]-skin[1],-2.5,2.5),clamp(shadow[2]-skin[2],-2.5,2.5)],samples:clean.length}
}
// 자기 자신을 기준으로 한 guided filter: 경계(눈코입 윤곽)는 살리고 잔결·모공·잡티만 흐림
function guidedSmooth(ch: Float32Array, w: number, h: number, r: number, eps: number) {
  const n = ch.length, sq = new Float32Array(n)
  for (let i = 0; i < n; i++) sq[i] = ch[i] * ch[i]
  const mean = boxBlur(ch, w, h, r), meanSq = boxBlur(sq, w, h, r)
  const A = new Float32Array(n), Bc = new Float32Array(n)
  for (let i = 0; i < n; i++) { const v = meanSq[i] - mean[i] * mean[i], a = v / (v + eps); A[i] = a; Bc[i] = mean[i] * (1 - a) }
  const mA = boxBlur(A, w, h, r), mB = boxBlur(Bc, w, h, r), out = new Float32Array(n)
  for (let i = 0; i < n; i++) out[i] = mA[i] * ch[i] + mB[i]
  return out
}

const lerp = (a: Pt, b: Pt, t: number): Pt => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
const dist = (a: Pt, b: Pt) => Math.hypot(a[0] - b[0], a[1] - b[1])

// 다각형 내부를 value로 채움 (스캔라인, 픽셀 중심 기준)
function fillPolygon(mask: Float32Array, w: number, h: number, poly: Pt[], value: number) {
  let minY = Infinity, maxY = -Infinity
  for (const [, y] of poly) { minY = Math.min(minY, y); maxY = Math.max(maxY, y) }
  const xs: number[] = []
  for (let y = Math.max(0, Math.ceil(minY - 0.5)); y <= Math.min(h - 1, Math.floor(maxY - 0.5)); y++) {
    const cy = y + 0.5
    xs.length = 0
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [xi, yi] = poly[i], [xj, yj] = poly[j]
      if ((yi > cy) !== (yj > cy)) xs.push(xi + (cy - yi) / (yj - yi) * (xj - xi))
    }
    xs.sort((a, b) => a - b)
    for (let k = 0; k + 1 < xs.length; k += 2) {
      for (let x = Math.max(0, Math.ceil(xs[k] - 0.5)); x <= Math.min(w - 1, Math.floor(xs[k + 1] - 0.5)); x++) mask[y * w + x] = value
    }
  }
}

// 눈 윤곽 사이를 곡선 보간해 끊김 없이 연결한다.
function smoothContour(points: Pt[]): Pt[] {
  const out: Pt[] = []
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[Math.max(0, i - 1)], b = points[i], c = points[i + 1], d = points[Math.min(points.length - 1, i + 2)]
    for (let step = 0; step < 8; step++) {
      const t = step / 8
      const coord = (k: 0 | 1) => .5 * (2*b[k] + (-a[k]+c[k])*t + (2*a[k]-5*b[k]+4*c[k]-d[k])*t*t + (-a[k]+3*b[k]-3*c[k]+d[k])*t*t*t)
      out.push([coord(0), coord(1)])
    }
  }
  out.push(points[points.length - 1])
  return out
}
// 얇은 사선은 픽셀 내부 16개 지점의 커버리지로 가장자리를 부드럽게 한다.
function fillSmoothPolygon(mask: Float32Array, w: number, h: number, poly: Pt[]) {
  // 4×4 표본 안티에일리어싱, 표본 줄마다 교차점을 한 번만 구해 구간으로 셈 (픽셀마다 변을 다 도는 방식보다 수십 배 빠름, 결과 같음)
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const [x, y] of poly) { if (x < minX) minX = x; if (x > maxX) maxX = x; if (y < minY) minY = y; if (y > maxY) maxY = y }
  const x0 = Math.max(0, Math.floor(minX)), x1 = Math.min(w - 1, Math.ceil(maxX)), y0 = Math.max(0, Math.floor(minY)), y1 = Math.min(h - 1, Math.ceil(maxY))
  if (x1 < x0 || y1 < y0) return
  const SUB = [.125, .375, .625, .875], count = new Float32Array(x1 - x0 + 1), xs: number[] = []
  for (let y = y0; y <= y1; y++) {
    count.fill(0)
    for (const dy of SUB) {
      const cy = y + dy
      xs.length = 0
      for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const [xi, yi] = poly[i], [xj, yj] = poly[j]
        if ((yi > cy) !== (yj > cy)) xs.push((xj - xi) * (cy - yi) / (yj - yi) + xi)
      }
      xs.sort((a, b) => a - b)
      // 짝수-홀수 규칙: 표본 px가 [xs[2k], xs[2k+1]) 안이면 안쪽
      for (let k = 0; k + 1 < xs.length; k += 2) {
        const a = xs[k], b = xs[k + 1]
        for (let x = Math.max(x0, Math.floor(a - .875)); x <= Math.min(x1, Math.ceil(b)); x++)
          for (const dx of SUB) { const px = x + dx; if (px >= a && px < b) count[x - x0]++ }
      }
    }
    for (let x = x0; x <= x1; x++) { const v = count[x - x0] / 16, i = y * w + x; if (v > mask[i]) mask[i] = v }
  }
}

function boxBlur(src: Float32Array, w: number, h: number, r: number): Float32Array {
  const tmp = new Float32Array(src.length), out = new Float32Array(src.length), d = 2 * r + 1
  for (let y = 0; y < h; y++) {
    const row = y * w
    let acc = 0
    for (let x = -r; x <= r; x++) acc += src[row + Math.min(w - 1, Math.max(0, x))]
    for (let x = 0; x < w; x++) {
      tmp[row + x] = acc / d
      acc += src[row + Math.min(w - 1, x + r + 1)] - src[row + Math.max(0, x - r)]
    }
  }
  for (let x = 0; x < w; x++) {
    let acc = 0
    for (let y = -r; y <= r; y++) acc += tmp[Math.min(h - 1, Math.max(0, y)) * w + x]
    for (let y = 0; y < h; y++) {
      out[y * w + x] = acc / d
      acc += tmp[Math.min(h - 1, y + r + 1) * w + x] - tmp[Math.max(0, y - r) * w + x]
    }
  }
  return out
}

// 가우시안 근사 (박스 블러 3번)
function blur(src: Float32Array, w: number, h: number, sigma: number): Float32Array {
  const r = Math.max(1, Math.round((Math.sqrt(4 * sigma * sigma + 1) - 1) / 2))
  return boxBlur(boxBlur(boxBlur(src, w, h, r), w, h, r), w, h, r)
}

// 회전된 타원 가우시안을 찍음 (겹치면 큰 값)
function stamp(mask: Float32Array, w: number, h: number, c: Pt, sx: number, sy: number, angle: number, weight = 1) {
  const cos = Math.cos(angle), sin = Math.sin(angle), R = 3 * Math.max(sx, sy)
  for (let y = Math.max(0, Math.floor(c[1] - R)); y <= Math.min(h - 1, Math.ceil(c[1] + R)); y++) {
    for (let x = Math.max(0, Math.floor(c[0] - R)); x <= Math.min(w - 1, Math.ceil(c[0] + R)); x++) {
      const dx = x + 0.5 - c[0], dy = y + 0.5 - c[1]
      const u = (dx * cos + dy * sin) / sx, v = (-dx * sin + dy * cos) / sy
      const g = weight * Math.exp(-0.5 * (u * u + v * v))
      const i = y * w + x
      if (g > mask[i]) mask[i] = g
    }
  }
}

// 이마 부채꼴 하이라이트: 미간(apex)에서 위로 갈수록 넓어지고 옅어짐 (일자로 올리면 미간에 흰 막대처럼 뜸)
function stampFan(mask: Float32Array, w: number, h: number, apex: Pt, top: Pt, faceW: number, roll: number, weight: number) {
  for (let t = 0; t <= 1; t += .1) {
    const ease = Math.min(1, t / .2)
    stamp(mask, w, h, lerp(apex, top, t), faceW * (.012 + .055 * t), faceW * .03, roll, weight * (.55 + .45 * ease) * (1 - .7 * t))
  }
}

// 피부 보정: 결 정리 비율·붉은기 완화 비율·쿠션 색으로 옮기는 비율 (강하면 플라스틱 피부)
const SKIN_SMOOTH = 0.7, SKIN_EVEN = 0.6, SKIN_TONE = 0.35
// 쿠션보다 밝은 피부에서 색감을 쿠션 쪽으로 옮기는 최소 비율
const SKIN_BRIGHT_PULL = .3
// 트러블 메우기: 피부 보정 강도에 곱하는 배율 (보정 55%면 거의 다 메움)
const SKIN_SPOT = 1.8
// 볼 집중 보정 (2026-11-15 "볼 피부보정 빡세게"): 볼 마스크 안에서 결 정리·붉은기 완화를 이만큼 더 (1이면 2배)
// 코 주변은 빼서 콧볼·팔자 그늘이 지워지지 않게
const CHEEK_SMOOTH = 1.3, CHEEK_EVEN = 1.6, CHEEK_NOSE_R = .09
// 쉐딩: 강도 1일 때 밝기(L*)를 내리는 양
const SHADE_DEPTH = 13
// 코·광대 분석 층 세기 (룩 쉐딩·하이라이터 세기에 곱함)
const FEAT_SHADE = 1.3, FEAT_HL = 1.8
// 코 맞춤 기법 층 배율 (룩 코 쉐딩 강도에 곱함, 여성 룩 코 강도가 .07~.3이라 그대로면 기법 차이가 안 보임)
const FIT_NOSE = 4, FIT_NOSE_MIN = .45
// 코끝 음영(U자·상자·콧볼 테두리) 배율 (콧대 선은 그대로, 코끝만 진하게)
const NOSE_TIP_GAIN = 1.3
// 하이라이터: 밝기(L*) 올리는 양(강도 1, 밝은 피부일수록 덜) · 채도 빼는 비율 · 하이라이터 색 쪽으로 옮기는 비율
const HL_LIFT = 40, HL_CHROMA = .2, HL_TINT = .25
// 수염 자국: 볼 피부와의 차이가 이만큼 넘는 곳부터, 이 범위에 걸쳐 0→1 / 가리는 세기(밝기·색감)
const BEARD_MIN = 2, BEARD_RANGE = 8, BEARD_L = 0.75, BEARD_AB = 0.9
// 윗눈꺼풀 보정: 랜드마크가 실제 속눈썹 라인보다 몇 px 위·아래로 잡히는 사진이 있음
// → 점마다 위쪽 법선 방향으로 훑어 '아래 어둡고 위 밝은' 경계(속눈썹 라인 윗선)를 찾음
// 쌍꺼풀 주름도 같은 경계라 먼 곳은 벌점, 명암 차가 작으면 그대로, 이웃 점과 중앙값으로 튀는 점 정리
const LID_SEARCH_UP = .08, LID_SEARCH_DOWN = .03, LID_MIN_EDGE = 6, LID_FAR_PENALTY = 8
function refineUpperLid(data: Uint8ClampedArray, w: number, h: number, pts: Pt[], eyeW: number): Pt[] {
  const luma = (x: number, y: number) => {
    let sum = 0, cnt = 0
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      const px = Math.round(x) + dx, py = Math.round(y) + dy
      if (px < 0 || py < 0 || px >= w || py >= h) continue
      const o = (py * w + px) * 4; sum += data[o] * .299 + data[o + 1] * .587 + data[o + 2] * .114; cnt++
    }
    return cnt ? sum / cnt : 0
  }
  const gap = Math.max(1, eyeW * .02), far = eyeW * LID_SEARCH_UP
  const shifts = pts.map((p, j) => {
    // 눈 양 끝(눈머리·눈꼬리)은 경계가 흐려 그대로
    if (j === 0 || j === pts.length - 1) return 0
    const a = pts[j - 1], b = pts[j + 1]
    let nx = b[1] - a[1], ny = -(b[0] - a[0])
    const len = Math.hypot(nx, ny) || 1
    nx /= len; ny /= len
    if (ny > 0) { nx = -nx; ny = -ny }
    let best = 0, bestScore = -Infinity, bestEdge = 0
    for (let t = -eyeW * LID_SEARCH_DOWN; t <= far; t += .5) {
      const edge = luma(p[0] + nx * (t + gap), p[1] + ny * (t + gap)) - luma(p[0] + nx * (t - gap), p[1] + ny * (t - gap))
      const score = edge - LID_FAR_PENALTY * Math.abs(t) / far
      if (score > bestScore) { bestScore = score; best = t; bestEdge = edge }
    }
    return bestEdge < LID_MIN_EDGE ? 0 : best
  })
  const smooth = shifts.map((_, j) => {
    if (j === 0 || j === shifts.length - 1) return 0
    return [shifts[j - 1], shifts[j], shifts[j + 1]].sort((x, y) => x - y)[1]
  })
  // 눈 양 끝은 이웃 점 이동의 절반만 따라감 (그대로 두면 끝에서 곡선이 꺾여 내려가 속눈썹 끝이 처지고 짧아 보임)
  smooth[0] = smooth[1] * .5
  smooth[smooth.length - 1] = smooth[smooth.length - 2] * .5
  return pts.map((p, j) => {
    if (!smooth[j]) return p
    const a = pts[Math.max(0, j - 1)], b = pts[Math.min(pts.length - 1, j + 1)]
    let nx = b[1] - a[1], ny = -(b[0] - a[0])
    const len = Math.hypot(nx, ny) || 1
    nx /= len; ny /= len
    if (ny > 0) { nx = -nx; ny = -ny }
    return [p[0] + nx * smooth[j], p[1] + ny * smooth[j]] as Pt
  })
}
// 속눈썹 시작점: 눈머리부터 눈 안쪽(위·아래 눈꺼풀 사이)을 훑어 흰자가 처음 보이는 곳 (눈 길이 비율)
// 몽고주름이 덮은 눈머리는 랜드마크상 눈 안이어도 피부·분홍 눈물언덕이라 흰자가 없음 → 그 앞은 속눈썹을 안 붙임
// 흰자: 눈 안 밝은 픽셀 상위 15% 밝기의 82% 이상 + 무채색, 한 열에서 30% 이상이면 보이는 것으로
const SCLERA_LUMA = .82, SCLERA_CHROMA = .28, SCLERA_FILL = .3, LASH_START_MAX = .4, LASH_START_NONE = .12
function visibleLashStart(data: Uint8ClampedArray, w: number, h: number, upper: Pt[], lower: Pt[]) {
  const o = upper[0], e = upper[upper.length - 1], L = dist(o, e) || 1
  const ux = (e[0] - o[0]) / L, uy = (e[1] - o[1]) / L
  // 눈 축 좌표 (t: 눈머리 0 → 눈꼬리 1, y: 축에서 수직 거리)
  const frame = (pts: Pt[]) => pts.map(([x, y]) => [((x - o[0]) * ux + (y - o[1]) * uy) / L, -(x - o[0]) * uy + (y - o[1]) * ux] as const)
  const U = frame(upper), Lw = frame(lower)
  const interp = (pts: readonly (readonly [number, number])[], t: number) => {
    let i = 0
    while (i < pts.length - 2 && t > pts[i + 1][0]) i++
    const [t0, y0] = pts[i], [t1, y1] = pts[i + 1]
    return y0 + (y1 - y0) * Math.min(1, Math.max(0, (t - t0) / ((t1 - t0) || 1)))
  }
  const pixel = (t: number, v: number) => {
    const yu = interp(U, t), yl = interp(Lw, t), y = yu + (yl - yu) * v
    const px = Math.round(o[0] + ux * L * t - uy * y), py = Math.round(o[1] + uy * L * t + ux * y)
    if (px < 0 || py < 0 || px >= w || py >= h) return null
    const k = (py * w + px) * 4, r = data[k], g = data[k + 1], b = data[k + 2], max = Math.max(r, g, b)
    return { luma: r * .299 + g * .587 + b * .114, chroma: max ? (max - Math.min(r, g, b)) / max : 0 }
  }
  const column = (t: number) => Array.from({ length: 9 }, (_, j) => pixel(t, .2 + .6 * j / 8)).filter(p => p !== null)
  const ref: number[] = []
  for (let t = .08; t < .4; t += .01) for (const p of column(t)) ref.push(p.luma)
  ref.sort((a, b) => a - b)
  const bright = ref[Math.floor(ref.length * .85)] ?? 0
  for (let t = 0; t < LASH_START_MAX; t += .01) {
    const col = column(t)
    if (col.length && col.filter(p => p.luma > bright * SCLERA_LUMA && p.chroma < SCLERA_CHROMA).length / col.length >= SCLERA_FILL) return t
  }
  return LASH_START_NONE
}
// 애교살 주름을 찾는 아래 두 번째 랜드마크 줄 (아래 눈꺼풀 점과 같은 순서: 눈머리 → 눈꼬리), 못 찾을 때 기본 깊이
const AEGYO_RING2: Record<number, number[]> = { 145: [244,233,232,231,230,229,228,31,226], 374: [464,453,452,451,450,449,448,261,446] }
const AEGYO_DEPTH = .6
// 애교살 섀도 강도 배율
const AEGYO_SHADOW = .75
// 섀도 크기 배율 (테스트 사진에서 레퍼런스와 비교해 정함)
const SHADOW_SCALE = 1.8
// 블러셔 외곽 흐림 폭(얼굴 너비 비율)·옅어지는 곡선 (1보다 크면 가장자리가 더 서서히)
const BLUSH_FEATHER = 0.07, BLUSH_FALLOFF = 2.2
// 얼굴형별 블러셔 자리 (얼굴 너비 비율): 위로·바깥으로 옮김, 바깥쪽 끝을 관자놀이로 올리는 기울기, 가로 폭 배율 (ref2)
const BLUSH_FIT: Record<FaceShape, { up: number; out: number; tilt: number; wide: number }> = {
  oval: { up: -.005, out: .01, tilt: .2, wide: 1.05 },
  round: { up: .035, out: .04, tilt: .5, wide: .85 },
  square: { up: -.015, out: -.015, tilt: 0, wide: 1 },
  long: { up: .025, out: -.005, tilt: 0, wide: 1.35 },
  heart: { up: .005, out: .015, tilt: .05, wide: 1.2 },
  diamond: { up: .02, out: -.035, tilt: .1, wide: 1 },
}
// 촉촉립: 물광(채도 올림) 없이 아주 옅은 반투명 윤기만 살짝
const LIP_GLOSS = 0.2

// 피부 트러블 찾기: 볼 피부 안에서 주변(얼굴 너비 1.5% 반경)보다 붉은(a) 정도로 점수를 매기고 (점은 남김),
// 작은 덩어리만 남김 (큰 덩어리 = 그늘·머리카락·콧구멍이라 지우면 얼굴이 뭉개짐), 콧구멍·코 밑은 따로 제외
// 메울 색: 같은 반경에서 트러블을 뺀 피부만 평균 (트러블이 섞이면 메운 자리가 얼룩짐)
// 볼에만: 볼 가운데(랜드마크 50·280)에서 얼굴 너비의 이 비율 안 (코·입·눈가는 원래 그늘·윤곽이라 메우면 이목구비가 지워짐)
// 감지 기준 3→2.2 (2026-11-15 볼 보정 강화, 옅은 트러블도 메움)
const SPOT_DARK = 2.2, SPOT_RED = 2.2, SPOT_RANGE = 6, SPOT_MAX_AREA = 0.03, CHEEK_RADIUS = 0.16
// 내 눈썹 빈 곳 채우기 (에셋 없이): 눈썹 윤곽 근처에서 주변 피부보다 어두운 털을 찾고,
// 털을 넓게 흐려 만든 "내 눈썹 범위" 안에서 털이 없는 틈만 남김 → 모양은 그대로, 숱만 채움
// 털 판정: 구간 밝기 상위(피부)·하위(털) 분위수 사이 비율, 둘 차이가 BROW_OWN_MIN_CONTRAST 미만이면 눈썹이 거의 없어 안 채움
const BROW_OWN_IDS = [[70, 63, 105, 66, 107, 55, 65, 52, 53, 46], [336, 296, 334, 293, 300, 276, 283, 282, 295, 285]]
const BROW_OWN_MIN_CONTRAST = 12
function ownBrowFill(data: Uint8ClampedArray, w: number, h: number, P: (i: number) => Pt, faceW: number): Float32Array {
  const n = w * h, out = new Float32Array(n)
  const luma = (i: number) => data[i * 4] * .299 + data[i * 4 + 1] * .587 + data[i * 4 + 2] * .114
  for (const ids of BROW_OWN_IDS) {
    const poly = ids.map(P)
    const hard = new Float32Array(n)
    fillPolygon(hard, w, h, poly, 1)
    // 털 찾는 구간: 윤곽보다 살짝 넓게 (랜드마크가 실제 눈썹보다 얇거나 어긋날 때), 채우는 범위: 윤곽 안쪽 위주
    const near = blur(hard, w, h, faceW * .012), inside = blur(hard, w, h, faceW * .004)
    const xs = poly.map(p => p[0]), ys = poly.map(p => p[1]), pad = faceW * .05
    const x0 = Math.max(0, Math.floor(Math.min(...xs) - pad)), x1 = Math.min(w - 1, Math.ceil(Math.max(...xs) + pad))
    const y0 = Math.max(0, Math.floor(Math.min(...ys) - pad)), y1 = Math.min(h - 1, Math.ceil(Math.max(...ys) + pad))
    const vals: number[] = []
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) { const i = y * w + x; if (near[i] > .05) vals.push(luma(i)) }
    if (vals.length < 30) continue
    vals.sort((a, b) => a - b)
    const hairL = vals[Math.floor(vals.length * .1)], skinL = vals[Math.floor(vals.length * .85)], range = skinL - hairL
    if (range < BROW_OWN_MIN_CONTRAST) continue
    const hair = new Float32Array(n)
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
      const i = y * w + x
      if (near[i] > .05) hair[i] = Math.min(1, Math.max(0, (skinL - luma(i) - range * .15) / (range * .6))) * Math.min(1, near[i] * 2)
    }
    // 내 눈썹 범위: 털을 넓게 흐린 뒤 정규화 (틈은 메워지고 바깥으로는 거의 안 번짐)
    const env = blur(hair, w, h, faceW * .01)
    let max = 0
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) max = Math.max(max, env[y * w + x])
    if (max <= 0) continue
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
      const i = y * w + x, t = Math.min(1, Math.max(0, (env[i] / max - .2) / .3))
      const e = t * t * (3 - 2 * t) * Math.min(1, inside[i] * 1.6)
      out[i] = Math.max(out[i], e * (1 - hair[i]))
    }
  }
  // 파우더처럼 살짝 흐림
  return blur(out, w, h, Math.max(.6, faceW * .002))
}

function findSpots(data: Uint8ClampedArray, W: number, H: number, faceW: number, skinFull: Float32Array, Lfull: Float32Array, Afull: Float32Array, noseFull: Pt[], cheeks: Pt[]) {
  // 피부가 있는 사각형만 잘라 계산 (사진 전체를 여러 번 흐리면 고해상도 사진에서 수 초 걸림)
  let x0 = W, y0 = H, x1 = -1, y1 = -1
  for (let i = 0; i < W * H; i++) if (skinFull[i] > .5) { const x = i % W, y = (i / W) | 0; if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y }
  const spotMaskFull = new Float32Array(W * H), spotFillFull = new Uint8ClampedArray(W * H * 3)
  if (x1 < 0) return { spotMask: spotMaskFull, spotFill: spotFillFull }
  const pad = Math.ceil(faceW * .05)
  x0 = Math.max(0, x0 - pad); y0 = Math.max(0, y0 - pad); x1 = Math.min(W - 1, x1 + pad); y1 = Math.min(H - 1, y1 + pad)
  const w = x1 - x0 + 1, h = y1 - y0 + 1, n = w * h
  const at = (i: number) => (y0 + ((i / w) | 0)) * W + x0 + (i % w)
  const r = Math.max(2, faceW * 0.015)
  const inSkin = new Float32Array(n), L = new Float32Array(n), A = new Float32Array(n)
  for (let i = 0; i < n; i++) { const k = at(i); inSkin[i] = skinFull[k] > .5 ? 1 : 0; L[i] = Lfull[k]; A[i] = Afull[k] }
  // 볼 영역만 메움 (주변 평균은 피부 전체로 계산해야 볼 가장자리가 튀지 않음)
  const cheekR = faceW * CHEEK_RADIUS, cheek = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const x = x0 + (i % w), y = y0 + ((i / w) | 0)
    for (const [cx, cy] of cheeks) {
      const d = Math.hypot(x - cx, y - cy) / cheekR
      if (d < 1) cheek[i] = Math.max(cheek[i], d < .7 ? 1 : (1 - d) / .3)
    }
  }
  // 콧구멍·콧볼·코 밑(인중 위) 제외: 원래 그늘진 자리라 메우면 하얗게 뜸
  const noseR = faceW * 0.07
  for (const [cx0, cy0] of noseFull) {
    const cx = cx0 - x0, cy = cy0 - y0
    for (let y = Math.max(0, Math.floor(cy - noseR)); y <= Math.min(h - 1, cy + noseR); y++) for (let x = Math.max(0, Math.floor(cx - noseR)); x <= Math.min(w - 1, cx + noseR); x++) if ((x - cx) ** 2 + (y - cy) ** 2 < noseR * noseR) inSkin[y * w + x] = 0
  }
  // 가중 평균 흐림 (같은 가중치는 분모를 한 번만 흐림)
  const avgWith = (weight: Float32Array, radius = r) => {
    const bw = blur(weight, w, h, radius)
    return (ch: Float32Array) => {
      const num = new Float32Array(n)
      for (let i = 0; i < n; i++) num[i] = ch[i] * weight[i]
      const bn = blur(num, w, h, radius)
      for (let i = 0; i < n; i++) bn[i] = bw[i] > 1e-3 ? bn[i] / bw[i] : ch[i]
      return bn
    }
  }
  const skinAvg = avgWith(inSkin), mL = skinAvg(L), mA = skinAvg(A)
  const hit = new Uint8Array(n), score = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    if (!inSkin[i] || !cheek[i]) continue
    // 점(어둡지만 안 붉음)은 남기고 붉은 트러블만: 붉은 정도가 기준, 어두움은 붉은 기가 있을 때만 더함 (붉은 자국)
    const red = A[i] - mA[i]
    const v = Math.max(0, (red - SPOT_RED) / SPOT_RANGE) + (red > SPOT_RED * .5 ? Math.max(0, (mL[i] - L[i] - SPOT_DARK) / SPOT_RANGE) * .6 : 0)
    if (v > 0) { score[i] = Math.min(1, v); hit[i] = 1 }
  }
  // 덩어리 크기 제한 (4방향 연결): 너무 큰 덩어리 = 그늘·머리카락이라 지움 대상에서 뺌
  const keepSmall = (hitMap: Uint8Array, sc: Float32Array, maxArea: number, keep?: (comp: number[]) => boolean) => {
    const seen = new Uint8Array(n), stack: number[] = [], comp: number[] = []
    for (let i = 0; i < n; i++) {
      if (!hitMap[i] || seen[i]) continue
      comp.length = 0; stack.push(i); seen[i] = 1
      while (stack.length) {
        const j = stack.pop()!; comp.push(j)
        const x = j % w
        for (const k of [j - 1, j + 1, j - w, j + w]) {
          if (k < 0 || k >= n || seen[k] || !hitMap[k] || (k === j - 1 && x === 0) || (k === j + 1 && x === w - 1)) continue
          seen[k] = 1; stack.push(k)
        }
      }
      if (comp.length > maxArea || (keep && !keep(comp))) for (const j of comp) sc[j] = 0
    }
  }
  keepSmall(hit, score, (faceW * SPOT_MAX_AREA) ** 2)
  // 경계를 살짝 넓혀 부드럽게
  const grown = blur(score, w, h, Math.max(1, r * .25)), spotMask = new Float32Array(n)
  for (let i = 0; i < n; i++) spotMask[i] = Math.min(1, Math.max(score[i], grown[i] * 2.2)) * inSkin[i] * cheek[i]
  // 메울 색: 트러블 아닌 피부만 평균
  const clean = new Float32Array(n)
  for (let i = 0; i < n; i++) clean[i] = inSkin[i] * (1 - Math.min(1, spotMask[i] * 2))
  const cleanAvg = avgWith(clean)
  const chans = [0, 1, 2].map(c => { const a = new Float32Array(n); for (let i = 0; i < n; i++) a[i] = data[at(i) * 4 + c]; return cleanAvg(a) })
  for (let i = 0; i < n; i++) {
    if (spotMask[i] <= .01) continue
    const k = at(i); spotMaskFull[k] = spotMask[i]
    for (let c = 0; c < 3; c++) spotFillFull[k * 3 + c] = chans[c][i]
  }
  return { spotMask: spotMaskFull, spotFill: spotFillFull }
}

// 보정량은 백엔드 분류 경계에서 계산한다. 분석이 없으면 추가 보정 없이 룩의 음영만 사용.
export type ShapeFeatures = { fit?: FaceFit | null; width_ratio: number; bulbous_ratio: number; upturn: number; cheek_width_ratio: number; cheek_correction?: { relative_width: number; wide: number; narrow: number }; nose_correction?: { wide_wings: number; round_tip: number; upturned: number; drooping: number }; face_shape?: string; face_ratios?: { length_width: number; forehead_cheek: number; jaw_cheek: number; lower_face: number } }
function shapeStrengths(f: ShapeFeatures | null | undefined) {
  if (!f) return { wideNose: 0, roundTip: 0, upturned: 0, drooping: 0, wideCheek: 0, narrowCheek: 0 }
  return {
    wideNose: f.nose_correction?.wide_wings ?? 0,
    roundTip: f.nose_correction?.round_tip ?? 0,
    upturned: f.nose_correction?.upturned ?? 0,
    drooping: f.nose_correction?.drooping ?? 0,
    wideCheek: f.cheek_correction?.wide ?? 0,
    narrowCheek: f.cheek_correction?.narrow ?? 0,
  }
}

export function prepareFace(image: { width: number; height: number; data: Uint8ClampedArray }, points: readonly (readonly number[])[], features?: ShapeFeatures | null): PreparedFace {
  const shape = shapeStrengths(features)
  const fit = features?.fit ?? null
  const FIT_KO: Record<FaceShape, string> = { oval: '계란형', round: '둥근형', square: '사각형', long: '긴형', heart: '하트형', diamond: '다이아몬드' }
  const faceShape = fit ? FIT_KO[fit.face] : features?.face_shape
  const ratios = features?.face_ratios
  const broadJaw = Math.max(faceShape === '사각형' ? .65 : 0, ratios ? Math.max(0, Math.min(1, (ratios.jaw_cheek - .78) / .07)) : 0)
  const cheekBone = 1 - .8 * shape.wideCheek, jawBone = 1 - .8 * broadJaw
  const { width: w, height: h, data } = image
  const n = w * h
  const P = (i: number): Pt => [points[i][0] * w, points[i][1] * h]
  const faceW = dist(P(234), P(454))
  const roll = Math.atan2(P(263)[1] - P(33)[1], P(263)[0] - P(33)[0])
  const center = P(4)

  // 얼굴 안쪽만 (가장자리는 부드럽게), 눈은 제외
  const ovalHard = new Float32Array(n)
  fillPolygon(ovalHard, w, h, FACE_OVAL.map(P), 1)
  const oval = blur(ovalHard, w, h, faceW * 0.02)
  const eyeHard = new Float32Array(n)
  fillPolygon(eyeHard, w, h, LEFT_EYE.map(P), 1)
  fillPolygon(eyeHard, w, h, RIGHT_EYE.map(P), 1)
  const eyes = blur(eyeHard, w, h, faceW * 0.008)
  const clip = (m: Float32Array) => { for (let i = 0; i < n; i++) m[i] = Math.min(1, Math.max(0, m[i])) * oval[i] * Math.max(0, 1 - eyes[i] * 2) }

  const shading = new Float32Array(n), highlight = new Float32Array(n), blush = new Float32Array(n)
  const blushDiagonal = new Float32Array(n), blushUnder = new Float32Array(n), blushWide = new Float32Array(n)
  const blushHangover = new Float32Array(n), blushTeary = new Float32Array(n), glowZone = new Float32Array(n)
  const blushSlim = new Float32Array(n), blushEnnui = new Float32Array(n), blushMid = new Float32Array(n)
  const jawV = new Float32Array(n), jawChin = new Float32Array(n), sculpt = new Float32Array(n)
  // 코·광대 분석 결과만 모은 층 (룩 음영과 겹쳐 묻히지 않게 따로 한 번 더 그림)
  const boneHighlight = new Float32Array(n)
  const featShade = new Float32Array(n), featHL = new Float32Array(n), noseCorrection = new Float32Array(n)
  const shadowBasic = new Float32Array(n), shadowWing = new Float32Array(n), shadowSmoky = new Float32Array(n), shadowLong = new Float32Array(n)
  const underOuter = new Float32Array(n), underFull = new Float32Array(n), underWide = new Float32Array(n), lidShine = new Float32Array(n)
  const aegyoLight = new Float32Array(n), aegyoShadow = new Float32Array(n), aegyoLong = new Float32Array(n), aegyoLongShadow = new Float32Array(n)
  for (const side of SIDES) {
    // 턱 쉐딩은 관자놀이에 넣지 않고 형태별로 턱선에만 배치.
    for (const i of side.jaw.slice(1)) stamp(shading, w, h, lerp(P(i), center, 0.08), faceW * 0.055, faceW * 0.06, roll, 0.85)
    const lowerJaw = side.apple === 50 ? [132, 58, 172, 136, 150] : [361, 288, 397, 365, 379]
    for (let j = 0; j < lowerJaw.length - 1; j++) {
      for (let t = 0; t <= 1; t += 0.25) stamp(jawV, w, h, lerp(lerp(P(lowerJaw[j]), P(lowerJaw[j + 1]), t), center, 0.04), faceW * 0.045, faceW * 0.04, roll, 0.95)
    }
    const chinSide = side.apple === 50 ? 149 : 378
    stamp(jawChin, w, h, lerp(P(chinSide), P(17), 0.12), faceW * 0.04, faceW * 0.035, roll, 0.9)
    // 블러셔는 같은 색이라도 볼 중앙·광대·눈 밑의 위치와 방향이 다름.
    // 얼굴형·광대 맞춤: 같은 블러셔 모양이라도 높이·바깥쪽·기울기·가로 폭을 얼굴마다 다르게 (ref2)
    const sgn = Math.sign(P(side.apple)[0] - center[0]) || 1
    const bf = fit ? BLUSH_FIT[fit.face] : BLUSH_FIT.oval
    const bOut = (fit ? bf.out : 0) + (fit ? (fit.cheek === 'wide' ? -.02 : fit.cheek === 'narrow' ? .02 : 0) : 0), bUp = fit ? bf.up : 0
    const bTilt = fit ? -sgn * bf.tilt : 0, bWide = fit ? bf.wide : 1
    const fitPt = (p: Pt): Pt => [p[0] + faceW * (sgn * bOut * Math.cos(roll) + bUp * Math.sin(roll)), p[1] + faceW * (sgn * bOut * Math.sin(roll) - bUp * Math.cos(roll))]
    const apple = fitPt(lerp(P(side.apple), P(side.outer), 0.25))
    const toTemple = Math.atan2(P(side.temple)[1] - apple[1], P(side.temple)[0] - apple[0])
    // 볼 중앙: 작은 원이면 진하게 올릴 때 동그란 도장처럼 보여 넓게
    stamp(blush, w, h, apple, faceW * 0.075 * bWide, faceW * 0.066, roll + bTilt)
    stamp(blushWide,w,h,lerp(apple,fitPt(P(side.under)),.15),faceW*.13*bWide,faceW*.075,roll+bTilt,.75)
    stamp(blushDiagonal, w, h, lerp(apple, fitPt(P(side.outer)), 0.35), faceW * 0.12, faceW * 0.047, toTemple)
    stamp(blushUnder, w, h, fitPt(lerp(P(side.under), P(side.apple), 0.25)), faceW * 0.125 * Math.max(1, bWide), faceW * 0.042, roll + bTilt * .5)
    // 눈 밑: 아래로 둥근 반달 (ref1 目の下, 가운데가 볼 쪽으로 처짐)
    stamp(blushUnder, w, h, fitPt(lerp(P(side.under), P(side.apple), 0.6)), faceW * 0.075, faceW * 0.05, roll, .8)
    // 슬림 사선 (ref1 細見え): 관자놀이 → 광대 바깥 → 볼 아래에서 안쪽으로 굽는 물방울
    {
      const eyeO = P(side.apple === 50 ? 33 : 263)
      const path = [lerp(eyeO, P(side.temple), .5), lerp(P(side.outer), P(side.under), .25), lerp(lerp(P(side.outer), P(side.jaw[2]), .45), P(side.apple), .15), lerp(lerp(P(side.jaw[2]), P(side.apple), .55), P(side.jaw[3]), .15)]
      for (let k = 0; k < path.length - 1; k++) for (let t = 0; t <= 1; t += .2) {
        const u = (k + t) / (path.length - 1), a = Math.atan2(path[k+1][1]-path[k][1], path[k+1][0]-path[k][0])
        stamp(blushSlim, w, h, lerp(path[k], path[k+1], t), faceW * (.035 + .02 * u), faceW * (.025 + .025 * u), a, .65 + .35 * u)
      }
    }
    // 나른한 (ref1 アンニュイ): 눈썹 꼬리 아래 → 눈꼬리 바깥 → 눈 밑 바깥으로 C자
    {
      const eyeO = P(side.apple === 50 ? 33 : 263), browT = P(side.apple === 50 ? 46 : 276)
      const path = [lerp(browT, P(side.temple), .25), lerp(eyeO, P(side.temple), .45), lerp(P(side.under), P(side.upper), .3), lerp(P(side.under), P(side.apple), .35)]
      for (let k = 0; k < path.length - 1; k++) for (let t = 0; t <= 1; t += .2) stamp(blushEnnui, w, h, lerp(path[k], path[k+1], t), faceW * .04, faceW * .035, roll, k === 0 ? .6 + .4 * t : 1)
    }
    // 중안부 짧게 (ref1 中顔面短縮): 볼 중앙보다 조금 높고 안쪽의 둥근 발색
    stamp(blushMid, w, h, lerp(lerp(P(side.apple), P(side.under), .35), P(side.apple === 50 ? 129 : 358), .12), faceW * .075, faceW * .068, roll)
    // 블러셔 광: 광대 윗부분(튀어나온 곳)에만 맺히게 한다.
    stamp(glowZone, w, h, lerp(lerp(P(side.under), P(side.upper), 0.45), P(side.apple), 0.3), faceW * 0.09, faceW * 0.045, roll + (side.apple === 50 ? 0.3 : -0.3))
    // 숙취: 눈 밑을 넓게 + 콧등 쪽으로 이어지는 가로 띠
    const lowerLid = P(side.apple === 50 ? 145 : 374)
    stamp(blushHangover, w, h, lerp(lerp(P(side.under), P(side.apple), 0.2), lowerLid, 0.15), faceW * 0.13, faceW * 0.055, roll)
    stamp(blushHangover, w, h, lerp(lerp(P(side.under), P(side.apple), 0.3), P(195), 0.5), faceW * 0.07, faceW * 0.035, roll, 0.75)
    // 울먹: 언더 라인 바로 아래 + 눈꼬리 아래쪽
    const eyeOuter = P(side.apple === 50 ? 33 : 263)
    stamp(blushTeary, w, h, lerp(lowerLid, P(side.under), 0.4), faceW * 0.07, faceW * 0.028, roll, 0.95)
    stamp(blushTeary, w, h, lerp(eyeOuter, P(side.under), 0.45), faceW * 0.04, faceW * 0.03, roll, 0.8)
    stamp(blushTeary, w, h, lerp(lerp(lowerLid, P(side.under), 0.6), P(side.apple), 0.3), faceW * 0.09, faceW * 0.04, roll, 0.5)
    // 하이라이터: 광대 위쪽 (눈 밑 바깥), 광대가 넓으면 안쪽으로 옮기고 옅게 (바깥을 밝히면 더 넓어 보임)
    const tilt = side.apple === 50 ? 0.35 : -0.35
    const cheekTop = lerp(lerp(P(side.under), P(side.upper), 0.5), P(side.apple), 0.15 + 0.4 * shape.wideCheek)
    stamp(highlight, w, h, cheekTop, faceW * 0.06 * (1 - 0.3 * shape.wideCheek), faceW * 0.025, roll + tilt, 0.9 * (1 - 0.55 * shape.wideCheek))
    stamp(boneHighlight,w,h,cheekTop,faceW*.055,faceW*.018,roll+tilt,.85*cheekBone)
    stamp(boneHighlight,w,h,lerp(P(side.apple===50?136:365),P(17),.18),faceW*.03,faceW*.018,roll,.45*jawBone)
    // 광대가 좁으면 광대 바깥 위쪽까지 밝혀 옆으로 입체감
    if (shape.narrowCheek > 0) for (const m of [featHL]) stamp(m, w, h, lerp(cheekTop, P(side.temple), 0.4), faceW * 0.06, faceW * 0.026, roll + tilt, 1.0 * shape.narrowCheek)
    // 골격(남성): 광대뼈 바로 아래 사선 음영 (귀 앞 → 입꼬리 방향 45%, 위가 진하고 입 쪽으로 옅게) + 턱선 옆
    {
      const ear = P(side.jaw[0]), mouth = P(side.apple === 50 ? 61 : 291), a = Math.atan2(mouth[1] - ear[1], mouth[0] - ear[0])
      for (let t = 0; t <= 1; t += 1 / 7) {
        const c = lerp(ear, mouth, 0.04 + 0.42 * t), down = faceW * 0.028
        stamp(sculpt, w, h, [c[0] - Math.sin(roll) * down, c[1] + Math.cos(roll) * down], faceW * 0.05, faceW * 0.022, a, 0.95 * cheekBone * (1 - 0.6 * t))
      }
      for (const i of side.jaw.slice(2)) stamp(sculpt, w, h, lerp(P(i), center, 0.08), faceW * 0.045, faceW * 0.05, roll, 0.6 * jawBone)
    }
    // 넓은 옆광대 보정은 바깥 경계에 넓고 옅게. 광대 밑 사선은 룩의 골격 강조에만 둔다.
    if(shape.wideCheek>0) stamp(featShade,w,h,lerp(P(side.jaw[0]),P(side.outer),.25),faceW*.035,faceW*.055,roll,.4*shape.wideCheek)

  }
  // 얼굴형은 분류와 연속 비율을 함께 사용. 세로가 긴 얼굴에 턱 옆을 더 깎지 않는다.
  const longFace = ratios ? Math.max(faceShape === '긴형' ? .4 : 0, Math.min(1, (ratios.length_width - 1.29) / .16)) : faceShape === '긴형' ? .6 : 0
  for (const side of SIDES) {
    const left = side.apple === 50
    if (broadJaw > 0 || faceShape === '둥근형') {
      const strength = Math.max(broadJaw, faceShape === '둥근형' ? .45 : 0) * (1 - .65 * longFace)
      for (const id of side.jaw.slice(2)) stamp(featShade,w,h,lerp(P(id),center,.10),faceW*.045,faceW*.045,roll,.65*strength)
    }
    if (faceShape === '하트형' || (ratios?.forehead_cheek ?? 0) > .78)
      stamp(featShade,w,h,lerp(P(left?54:284),P(9),.12),faceW*.045,faceW*.05,roll,.35)
    // 긴형: 이마·턱끝을 짧게 눌러주고 볼은 가로로 밝힌다.
    if (longFace > 0) stamp(featHL,w,h,lerp(P(side.apple),P(side.under),.35),faceW*.075,faceW*.025,roll,.45*longFace)
    // 다이아몬드: 넓은 광대 바깥 대신 좁은 이마·턱 양옆을 살린다.
    if (!fit && faceShape === '다이아몬드') {
      stamp(featHL,w,h,lerp(P(left?54:284),P(9),.22),faceW*.035,faceW*.04,roll,.3)
      stamp(featHL,w,h,lerp(P(left?136:365),P(17),.3),faceW*.035,faceW*.025,roll,.25)
    }
    if (fit) {
      const sgn = Math.sign(P(side.apple)[0] - center[0]) || 1
      const out = (p: Pt, d: number): Pt => [p[0] + sgn * d * faceW * Math.cos(roll), p[1] + sgn * d * faceW * Math.sin(roll)]
      const underEye = lerp(lerp(P(side.under), P(side.apple), .3), P(left ? 133 : 362), .25)
      const browTail = P(left ? 46 : 276), eyeOuter = P(left ? 33 : 263), eyeInner = P(left ? 133 : 362), mouth = P(left ? 61 : 291)
      if (fit.face === 'oval') stamp(featHL,w,h,underEye,faceW*.04,faceW*.02,roll-sgn*.5,.5)
      if (fit.face === 'heart') {
        // 턱 양옆 세로로 밝혀 좁은 아래를 채움 + 눈 밑 바깥 사선
        stamp(featHL,w,h,lerp(P(side.jaw[3]),mouth,.35),faceW*.025,faceW*.06,roll+sgn*.25,.55)
        stamp(featHL,w,h,lerp(P(side.under),P(side.upper),.4),faceW*.045,faceW*.017,roll-sgn*.45,.45)
      }
      if (fit.face === 'diamond') {
        // 눈썹 위 이마 양옆 + 입꼬리 옆 괄호
        stamp(featHL,w,h,lerp(P(left?105:334),P(left?54:284),.3),faceW*.045,faceW*.02,roll,.5)
        for (let t = 0; t <= 1; t += .2) stamp(featHL,w,h,out(lerp(lerp(mouth,P(left?186:410),.5),lerp(mouth,P(left?204:424),.6),t),.018+.008*Math.sin(Math.PI*t)),faceW*.014,faceW*.016,roll,.4*Math.sin(Math.PI*(.15+.7*t)))
      }
      if (fit.face === 'square') {
        // 눈 둘레 C자: 눈썹 꼬리 아래 눈썹뼈 + 눈머리 옆
        stamp(featHL,w,h,lerp(browTail,eyeOuter,.4),faceW*.03,faceW*.012,roll-sgn*.6,.5)
        stamp(featHL,w,h,lerp(eyeInner,P(168),.45),faceW*.01,faceW*.02,roll,.45)
      }
      if (fit.face === 'round') stamp(featHL,w,h,underEye,faceW*.03,faceW*.015,roll-sgn*.7,.35)
    }
  }
  // 얼굴형별 가운데 하이라이트 (ref2): 이마 Y·세로, 턱끝 점·세로, 이마 가로 띠
  if (fit) {
    const forehead = lerp(P(151), P(9), .5), chin = lerp(P(17), P(152), .55)
    if (fit.face === 'oval' || fit.face === 'round') {
      // 이마: 미간에서 위로 넓게 퍼지는 부채꼴 (둥근형은 이마 위까지 길게)
      stampFan(featHL,w,h,lerp(P(9),P(168),.3),fit.face === 'round' ? lerp(P(151),P(10),.4) : P(151),faceW,roll,.5)
    }
    if (fit.face === 'heart') stamp(featHL,w,h,forehead,faceW*.06,faceW*.018,roll,.35)
    if (fit.face === 'diamond' || fit.face === 'square' || fit.face === 'oval' || fit.face === 'heart') stamp(featHL,w,h,chin,faceW*.022,faceW*.018,roll,.55)
    // 둥근형: 턱끝을 세로로 길게 밝혀 얼굴이 길어 보이게
    if (fit.face === 'round') stamp(featHL,w,h,lerp(P(17),P(152),.6),faceW*.016,faceW*.035,roll,.6)
  }
  if (longFace > 0) {
    stamp(featShade,w,h,lerp(P(10),P(9),.18),faceW*.10,faceW*.028,roll,.55*longFace)
    stamp(featShade,w,h,lerp(P(152),P(17),.10),faceW*.065,faceW*.025,roll,.55*longFace)
  }
  // 애교살 아래 주름 깊이: 아래 눈꺼풀 점 → 그 아래 두 번째 랜드마크 줄 선분 위에서 가장 어두운 곳 (선분 비율)
  // 주름이 안 보이는 얼굴(명암 차 작음)은 기본 깊이, 점마다 튀지 않게 이웃과 중앙값
  const aegyoDepth: Record<number, number[]> = {}
  for (const lid of [145, 374]) {
    const ids = lid === 145 ? [133,155,154,153,145,144,163,7,33] : [362,382,381,380,374,373,390,249,263]
    const raw = ids.map((id, j) => {
      const a = P(id), b = P(AEGYO_RING2[lid][j]), steps = Math.max(8, Math.round(dist(a, b)))
      let best = AEGYO_DEPTH, bestL = Infinity, maxL = -Infinity
      for (let s = 0; s <= steps; s++) {
        const f = .3 + .7 * s / steps, [x, y] = lerp(a, b, f)
        let sum = 0, cnt = 0
        for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
          const px = Math.round(x) + dx, py = Math.round(y) + dy
          if (px < 0 || py < 0 || px >= w || py >= h) continue
          const o = (py * w + px) * 4; sum += data[o] * .299 + data[o + 1] * .587 + data[o + 2] * .114; cnt++
        }
        const L = cnt ? sum / cnt : 0
        if (L < bestL) { bestL = L; best = f }
        if (L > maxL) maxL = L
      }
      return maxL - bestL < 4 ? AEGYO_DEPTH : best
    })
    aegyoDepth[lid] = raw.map((_, j) => {
      const near = [raw[Math.max(0, j - 1)], raw[j], raw[Math.min(raw.length - 1, j + 1)]].sort((x, y) => x - y)
      return Math.min(.9, Math.max(.35, near[1]))
    })
  }
  // 눈꺼풀 곡선을 따라 색을 채우고 가장자리만 부드럽게 한다.
  const linerBasic = new Float32Array(n), linerWing = new Float32Array(n), linerDown = new Float32Array(n), linerLongWing = new Float32Array(n), linerLongDown = new Float32Array(n)
  const upperLid: Record<number, Pt> = {}, lashStart = { left: 0, right: 0 }
  for (const eye of [
    { inner: 133, outer: 33, brow: 105, lower: 145, upper: [133, 173, 157, 158, 159, 160, 161, 246, 33] },
    { inner: 362, outer: 263, brow: 334, lower: 374, upper: [362, 398, 384, 385, 386, 387, 388, 466, 263] },
  ]) {
    const inner = P(eye.inner), outer = P(eye.outer), brow = P(eye.brow)
    const eyeW = dist(inner, outer)
    const mid = P(eye.upper[4]), upLength = Math.max(1, dist(mid, brow))
    const up: Pt = [(brow[0] - mid[0]) / upLength, (brow[1] - mid[1]) / upLength]
    // 윗눈꺼풀: 랜드마크를 사진 속 실제 속눈썹 라인 윗경계로 맞춤 (아이라인·속눈썹 공통)
    const upper = refineUpperLid(data, w, h, eye.upper.map(P), eyeW)
    eye.upper.forEach((id, j) => { upperLid[id] = upper[j] })
    lashStart[eye.inner === 133 ? 'left' : 'right'] = visibleLashStart(data, w, h, eye.upper.map(P), (eye.lower === 145 ? [133, 155, 154, 153, 145, 144, 163, 7, 33] : [362, 382, 381, 380, 374, 373, 390, 249, 263]).map(P))
    const outward: Pt = [(outer[0] - inner[0]) / eyeW, (outer[1] - inner[1]) / eyeW]
    const offset = (point: Pt, distance: number): Pt => [point[0] + up[0] * distance, point[1] + up[1] * distance]
    // 눈두덩을 단색 다각형으로 채우지 않고 속눈썹 가까운 곳부터 위로 부드럽게 소실시킨다.
    // 섀도 크기 기준 (눈 너비 그대로면 반경 3px 띠라 최대 강도에도 거의 안 보임 → 눈두덩을 덮게 키움)
    // 속눈썹에서 띄우는 거리는 눈 너비 그대로 (같이 키우면 섀도가 쌍꺼풀 위로 떠 줄처럼 보임)
    const sw=eyeW*SHADOW_SCALE
    const lash = smoothContour(upper)
    // 눈두덩 펄: 속눈썹 라인 위 눈두덩 가운데
    stamp(lidShine,w,h,offset(lash[Math.floor(lash.length/2)],eyeW*.08),eyeW*.24,eyeW*.07,Math.atan2(outward[1],outward[0]),1)
    const angle = Math.atan2(outward[1], outward[0])
    for(let i=0;i<lash.length;i+=2) {
      const t=i/(lash.length-1), taper=Math.sin(Math.PI*t)**.65
      const point=lash[i]
      // 기본: 낮은 높이의 색 번짐, 앞머리와 눈썹 아래 여백 유지.
      stamp(shadowBasic,w,h,offset(point,eyeW*.045),sw*.065,sw*.055,angle,taper)
      // 눈꼬리: 안쪽은 비우고 바깥 1/3에 깊이를 준다.
      const outerFocus=Math.min(1,Math.max(0,(t-.48)/.32))
      stamp(shadowWing,w,h,offset(point,eyeW*.055),sw*.09,sw*.08,angle,taper*outerFocus)
      // 스머지: 눈 전체를 높은 돔으로 칠하지 않고 속눈썹 가까이에 밀도 집중.
      stamp(shadowSmoky,w,h,offset(point,eyeW*.025),sw*.07,sw*.105,angle,taper)
      // 꼬리 길게: 가운데부터 바깥으로 갈수록 진하게 (눈꼬리에서 안 끊기게 taper 대신 끝까지 유지)
      const longFocus=Math.min(1,Math.max(0,(t-.35)/.45))
      stamp(shadowLong,w,h,offset(point,eyeW*.05),sw*.09,sw*.075,angle,longFocus*Math.max(taper,.6))
    }
    // 눈꼬리 뒤로 눈 너비의 25%까지 살짝 올려 빼고, 멀어질수록 얇고 옅게
    // (키운 섀도 기준 sw로 재면 눈 너비의 63%까지 나가 너무 길어서 눈 너비 기준)
    for(let k=0;k<=8;k++) {
      const u=k/8, along=eyeW*(.02+.23*u), lift=eyeW*(.03+.03*u)
      const point: Pt=[outer[0]+outward[0]*along+up[0]*lift,outer[1]+outward[1]*along+up[1]*lift]
      stamp(shadowLong,w,h,point,sw*(.09-.04*u),sw*(.06-.03*u),angle-.25*Math.sign(outward[0]||1),.85*(1-u*.7))
    }
    const extension: Pt=[outer[0]+outward[0]*sw*.07+up[0]*sw*.025,outer[1]+outward[1]*sw*.07+up[1]*sw*.025]
    stamp(shadowWing,w,h,extension,sw*.11,sw*.045,angle,.7)
    const lowerIds=eye.lower===145?[133,155,154,153,145,144,163,7,33]:[362,382,381,380,374,373,390,249,263]
    const lower=smoothContour(lowerIds.map(P))
    // 꼬리 길게: 언더 바깥 40%를 꼬리 끝 쪽으로 이어 V자로
    for(let i=Math.floor(lower.length*.6);i<lower.length;i+=2) {
      const t=(i/(lower.length-1)-.6)/.4
      stamp(shadowLong,w,h,offset(lower[i],-sw*.03),sw*.06,sw*.035,angle,.55*t)
    }
    // 아래 눈가: 아래 속눈썹 라인 바로 아래 띠, 눈머리 쪽은 옅게 (전체) / 바깥 절반만 (바깥쪽)
    for(let i=0;i<lower.length;i+=2) {
      const t=i/(lower.length-1)
      const point=offset(lower[i],-eyeW*.04)
      stamp(underFull,w,h,point,sw*.06,sw*.045,angle,.85*Math.min(1,.35+t)*Math.min(1,(1-t)*6+.4))
      stamp(underOuter,w,h,point,sw*.06,sw*.045,angle,.9*Math.min(1,Math.max(0,(t-.4)/.35))*Math.min(1,(1-t)*6+.4))
      // 넓게: 조금 더 아래까지 넓고 고르게 (도치, 진하기는 강도로 낮춤)
      stamp(underWide,w,h,offset(lower[i],-eyeW*.06),sw*.08,sw*.07,angle,.8*Math.min(1,.3+t)*Math.min(1,(1-t)*5+.3))
    }
    // 애교살: 아래 속눈썹 라인을 따라가는 얇은 띠 + 그 아래 옅은 음영 선 (눈매 곡선을 그대로 따라감)
    // 주름 위치는 사진에서 찾되 눈 너비 7~11% 안으로만 (찾은 깊이를 그대로 쓰면 볼까지 내려가 볼록한 덩어리가 됨)
    // 띠는 점마다 그 자리 눈매 기울기로 돌리고, 아래 방향도 그 자리 수직 방향 (눈 전체 한 방향으로 내리면 눈꼬리 쪽이 어긋남)
    const crease=smoothContour(lowerIds.map((id,j)=>lerp(P(id),P(AEGYO_RING2[eye.lower][j]),aegyoDepth[eye.lower][j])))
    for(let i=0;i<lower.length;i++) {
      const t=i/(lower.length-1)
      const a=lower[Math.max(0,i-1)], b=lower[Math.min(lower.length-1,i+1)]
      const tang=Math.atan2(b[1]-a[1],b[0]-a[0])
      let nx=-(b[1]-a[1]), ny=b[0]-a[0]
      const len=Math.hypot(nx,ny)||1
      nx/=len; ny/=len
      if (nx*up[0]+ny*up[1]>0) { nx=-nx; ny=-ny }
      const depth=Math.min(eyeW*.11,Math.max(eyeW*.07,dist(lower[i],crease[i])))
      const at=(d:number):Pt=>[lower[i][0]+nx*d,lower[i][1]+ny*d]
      // 기본: 눈머리~가운데 위주 / 길게: 눈꼬리 가까이까지 고르게
      for (const [light,line,fade] of [[aegyoLight,aegyoShadow,Math.sin(Math.PI*Math.min(1,t/.85))],[aegyoLong,aegyoLongShadow,Math.min(1,t/.2)*Math.min(1,(1-t)/.15)]] as const) {
        if (fade<=0) continue
        stamp(light,w,h,at(depth*.42),eyeW*.035,Math.max(1,depth*.28),tang,fade)
        stamp(line,w,h,at(depth),eyeW*.035,Math.max(.8,depth*.1),tang,fade*.7)
      }
    }
    // 언더는 바깥 1/3만 연결해 둥근 다크서클처럼 둘러싸지 않는다.
    for(let i=Math.floor(lower.length*.62);i<lower.length;i+=2) {
      const t=i/(lower.length-1)
      const point=offset(lower[i],-eyeW*.025)
      stamp(shadowSmoky,w,h,point,sw*.065,sw*.04,angle,.65*Math.sin(Math.PI*t))
    }
    // 눈축에 수직인 방향으로 두께를 준다. 눈썹 위치가 꼬리 방향을 비틀지 않게 한다.
    let normal: Pt = [outward[1], -outward[0]]
    if (normal[0]*up[0]+normal[1]*up[1]<0) normal = [-normal[0], -normal[1]]
    const lift = (point: Pt, height: number): Pt => [point[0]+normal[0]*height, point[1]+normal[1]*height]
    // 중앙 두께·바깥 두께·꼬리 길이·꼬리 높이·두꺼워지기 시작하는 위치 (눈 너비 비율).
    // 레퍼런스: 기본=짧은 브라운(5·12), 올림=길게 위로 뺀 윙(3), 내림=처진 강아지 라인(7)
    // (예전 두께 .025·윙 꼬리 .10·높이 0은 테스트 사진에서 1~2px라 라인이 거의 안 보임)
    for (const [mask, middle, outerThickness, tail, tipHeight, outerFocus] of [
      [linerBasic,.042,.055,0,0,.55],
      [linerWing,.03,.05,.26,.07,.45],
      [linerDown,.035,.055,.18,-.05,.5],
      [linerLongWing,.03,.05,.36,.09,.42],
      [linerLongDown,.035,.055,.25,-.06,.48],
    ] as const) {
      const top = lash.map((point,i) => {
        const t=i/(lash.length-1)
        const outerT=Math.max(0,Math.min(1,(t-outerFocus)/(1-outerFocus)))
        const blend=outerT*outerT*(3-2*outerT)
        const thickness=(middle+(outerThickness-middle)*blend)*Math.min(1,t/.22)
        return lift(point,eyeW*thickness)
      })
      if (!tail) {
        fillSmoothPolygon(mask,w,h,[...lash,...top.slice().reverse()])
        continue
      }
      const tip: Pt = [outer[0]+outward[0]*eyeW*tail+normal[0]*eyeW*tipHeight,outer[1]+outward[1]*eyeW*tail+normal[1]*eyeW*tipHeight]
      const start=top[top.length-1]
      const lowerEdge: Pt[]=[], upperEdge: Pt[]=[]
      // 위아래 경계를 같은 끝점에 연결해 꼬리가 눈에서 뜨거나 바늘처럼 꺾이지 않게 한다.
      const curve=(from:Pt,control:Pt,t:number):Pt=>{
        const u=1-t
        return [u*u*from[0]+2*u*t*control[0]+t*t*tip[0],u*u*from[1]+2*u*t*control[1]+t*t*tip[1]]
      }
      const lowerControl: Pt=[outer[0]+outward[0]*eyeW*tail*.52,outer[1]+outward[1]*eyeW*tail*.52]
      const upperControl: Pt=[start[0]+outward[0]*eyeW*tail*.50,start[1]+outward[1]*eyeW*tail*.50]
      for(let step=1;step<=20;step++)lowerEdge.push(curve(outer,lowerControl,step/20))
      for(let step=19;step>=0;step--)upperEdge.push(curve(start,upperControl,step/20))
      fillSmoothPolygon(mask,w,h,[...lash,...lowerEdge,...upperEdge,...top.slice(0,-1).reverse()])

    }
  }

  // 작은 블러로 라인의 픽셀 경계만 정돈. 안구는 정확하게 보호한다.
  for (const mask of [linerBasic, linerWing, linerDown, linerLongWing, linerLongDown]) {
    const softened = blur(mask, w, h, .35)
    for (let i = 0; i < n; i++) mask[i] = eyeHard[i] ? 0 : Math.min(1, (mask[i] * .8 + softened[i] * .2) * oval[i])
  }
  const cheekHighlight = highlight.slice(), centerHighlight = new Float32Array(n)
  const noseShading = new Float32Array(n), noseSlim = new Float32Array(n), noseTip = new Float32Array(n)
  const noseSculpted = new Float32Array(n), noseVTip = new Float32Array(n), noseWings = new Float32Array(n)
  const noseW = dist(P(129),P(358)), noseAccent = new Float32Array(n)
  // 사진별 실제 옆면 점을 잇는다. 코끝을 중심으로 평행선을 그리지 않는다.
  const noseStroke = (mask:Float32Array,ids:readonly [number,number,number,number],width:number,strength:number) => {
    const [a,b,c,d]=ids.map(P)
    for(let step=0;step<=32;step++){
      const t=step/32,u=1-t
      const p:Pt=[u*u*u*a[0]+3*u*u*t*b[0]+3*u*t*t*c[0]+t*t*t*d[0],u*u*u*a[1]+3*u*u*t*b[1]+3*u*t*t*c[1]+t*t*t*d[1]]
      const taper=Math.sin(Math.PI*(.08+.84*t))
      stamp(mask,w,h,p,noseW*width,noseW*.075,roll,strength*taper)
    }
  }
  for(const ids of [[193,122,3,51],[417,351,248,281]] as const){
    noseStroke(noseShading,ids,.065,.34)
    noseStroke(noseSlim,ids,.05,.43)
    noseStroke(noseSculpted,ids,.055,.48)
    noseStroke(noseVTip,ids,.06,.28)
  }
  // ref4/ref5: 코끝의 밝은 면을 남기는 열린 U자. 콧대 선과 코끝 윤곽은 연결하지 않는다.
  const tipCenter=lerp(P(4),P(1),.08)
  const lateral=(p:Pt)=>(p[0]-P(4)[0])*Math.cos(roll)+(p[1]-P(4)[1])*Math.sin(roll)
  const tipLeft=Math.min(noseW*.24,Math.max(noseW*.16,Math.abs(lateral(P(45)))*.85))
  const tipRight=Math.min(noseW*.24,Math.max(noseW*.16,Math.abs(lateral(P(275)))*.85))
  const tipDepth=dist(P(4),P(1))*.65
  const tipAt=(x:number,y:number):Pt=>[tipCenter[0]+x*Math.cos(roll)-y*Math.sin(roll),tipCenter[1]+x*Math.sin(roll)+y*Math.cos(roll)]
  const tipRound=new Float32Array(n)
  for(let step=0;step<=48;step++){
    const t=step/48,angle=-Math.PI*.15+Math.PI*1.3*t
    const radius=Math.cos(angle)<0?tipLeft:tipRight
    const c=tipAt(Math.cos(angle)*radius,Math.sin(angle)*tipDepth)
    const edge=.65+.35*Math.sin(Math.PI*t)
    stamp(tipRound,w,h,c,noseW*.047,noseW*.045,roll,.72*edge*NOSE_TIP_GAIN)
  }
  // 각진 골격 룩은 같은 실제 코끝 범위에서 짧은 면으로 꺾는다.
  const corners=[tipAt(-tipLeft*.7,-tipDepth*.45),tipAt(-tipLeft,tipDepth*.2),tipAt(-tipLeft*.6,tipDepth*.85),tipAt(0,tipDepth),tipAt(tipRight*.6,tipDepth*.85),tipAt(tipRight,tipDepth*.2),tipAt(tipRight*.7,-tipDepth*.45)]
  for(let k=0;k<corners.length-1;k++)for(let step=0;step<=8;step++)
    stamp(noseSculpted,w,h,lerp(corners[k],corners[k+1],step/8),noseW*.047,noseW*.045,roll,.68)
  for(const [shoulder,lower,bottom,upper,outer] of [[45,64,98,49,48],[275,294,327,279,278]] as const){
    noseStroke(noseWings,[upper,outer,lower,bottom],.065,.5)
    noseStroke(noseCorrection,[upper,outer,lower,bottom],.07,.4*shape.wideNose)
    stamp(noseCorrection,w,h,lerp(P(4),P(shoulder),.6),noseW*.05,noseW*.07,roll,.3*shape.roundTip)
  }
  // 코 맞춤 기법 (ref4·ref5): 분석한 코 타입마다 음영 모양이 확실히 다르게 (룩의 코 쉐딩과 겹쳐 그림)
  if (fit) {
    const bridgeIds = [[193,122,3,51],[417,351,248,281]] as const
    const tipBright = lerp(P(4),P(1),.1)
    if (fit.nose === 'straight') {
      // 直鼻: 눈썹 머리부터 코끝까지 끊김 없는 곧은 두 줄 + 가운데 긴 하이라이트
      for (const ids of bridgeIds) noseStroke(noseCorrection,ids,.05,.6)
      // 코끝은 열린 U자로 감싸 콧대 선과 이어지게
      for(let step=0;step<=40;step++){const t=step/40,a=-Math.PI*.1+Math.PI*1.2*t;stamp(noseCorrection,w,h,tipAt(Math.cos(a)*(Math.cos(a)<0?tipLeft:tipRight),Math.sin(a)*tipDepth),noseW*.045,noseW*.045,roll,.6*NOSE_TIP_GAIN*(.6+.4*Math.sin(Math.PI*t)))}
      for (let t = 0; t <= 1; t += 1/8) stamp(featHL,w,h,lerp(P(168),P(4),t),noseW*.05,noseW*.06,roll,.55)
      stamp(featHL,w,h,tipBright,noseW*.08,noseW*.055,roll,.75)
    }
    if (fit.nose === 'wing') {
      // 欧式: 콧볼을 감싸는 테두리 진하게 + 콧대 위쪽 평행선, 코끝 가운데 밝게
      for (const [lower,bottom,upper,outer] of [[64,98,49,48],[294,327,279,278]] as const) noseStroke(noseCorrection,[upper,outer,lower,bottom],.075,.75*NOSE_TIP_GAIN)
      for (const ids of bridgeIds) noseStroke(noseCorrection,ids,.045,.35)
      stamp(featHL,w,h,tipBright,noseW*.09,noseW*.06,roll,.8)
      for (let t = 0; t <= 1; t += 1/5) stamp(featHL,w,h,lerp(P(6),P(195),t),noseW*.04,noseW*.06,roll,.45)
    }
    if (fit.nose === 'box') {
      // 盒型: 코끝 양옆·아래를 각진 상자로 (위는 열어 둠), 상자 안 코끝을 밝게
      const box=[tipAt(-tipLeft*1.05,-tipDepth*.7),tipAt(-tipLeft*1.05,tipDepth*.85),tipAt(tipRight*1.05,tipDepth*.85),tipAt(tipRight*1.05,-tipDepth*.7)]
      for(let k=0;k<box.length-1;k++)for(let step=0;step<=10;step++) stamp(noseCorrection,w,h,lerp(box[k],box[k+1],step/10),noseW*.045,noseW*.045,roll,.8*NOSE_TIP_GAIN)
      stamp(featHL,w,h,tipBright,noseW*.1,Math.max(noseW*.05,tipDepth*.35),roll,.9)
    }
    // 코 옆 볼 밝은 면: 곧은 콧대 기법에만
    if (fit.nose === 'straight') for (const side of SIDES) {
      const c = lerp(lerp(P(side.apple), P(side.apple === 50 ? 129 : 358), .45), P(side.under), .3)
      stamp(featHL,w,h,c,faceW*.03,faceW*.02,roll+(side.apple===50?-.5:.5),.35)
    }
  }
  // 도식의 밝은 코끝 면 + 콧대의 짧은 하이라이트. 코끝 중앙은 쉐딩으로 채우지 않는다.
  stamp(noseAccent,w,h,lerp(P(4),P(1),.03),noseW*.085,Math.max(noseW*.045,tipDepth*.3),roll,.8)
  stamp(noseAccent,w,h,lerp(P(6),P(195),.75),noseW*.04,noseW*.12,roll,.5)
  for(let i=0;i<n;i++){
    noseTip[i]=Math.max(noseTip[i],tipRound[i])
    noseVTip[i]=Math.max(noseVTip[i],tipRound[i]*.85)
    noseSlim[i]=Math.max(noseSlim[i],tipRound[i]*.5)
    noseShading[i]=Math.max(noseShading[i],tipRound[i]*.35)
  }
  for(let i=0;i<n;i++){
    noseShading[i]=Math.max(noseShading[i],noseWings[i]*.35)
    noseSlim[i]=Math.max(noseSlim[i],noseWings[i]*.65)
    noseSculpted[i]=Math.max(noseSculpted[i],noseWings[i])
    noseTip[i]=Math.max(noseTip[i],noseWings[i]*.8)
    noseVTip[i]=Math.max(noseVTip[i],noseWings[i]*.85)
  }
  for(let i=0;i<n;i++) noseTip[i]=Math.max(noseTip[i],noseShading[i]*.7)
  // 코 주변 범위를 명시하고 콧구멍·코밑은 제외한다.
  const noseSupport=new Float32Array(n)
  fillPolygon(noseSupport,w,h,[193,168,417,351,419,248,281,275,440,358,294,327,2,98,64,129,220,45,51,3,196,122].map(P),1)
  const noseFeather=blur(noseSupport,w,h,Math.max(1,noseW*.035))
  const noseMasks=[noseShading,noseSlim,noseTip,noseSculpted,noseVTip,noseWings,noseCorrection]
  const smooth=(v:number)=>{const t=Math.max(0,Math.min(1,v));return t*t*(3-2*t)}
  const brightness=(p:Pt)=>{
    let sum=0,count=0
    for(let dy=-2;dy<=2;dy++)for(let dx=-2;dx<=2;dx++){
      const x=Math.round(p[0])+dx,y=Math.round(p[1])+dy
      if(x>=0&&x<w&&y>=0&&y<h){const i=(y*w+x)*4;sum+=data[i]*.299+data[i+1]*.587+data[i+2]*.114;count++}
    }
    return sum/Math.max(1,count)
  }
  const noseSkin=(brightness(P(49))+brightness(P(279)))/2
  const gap=lerp(P(6),P(195),.45)
  const gapY=-(gap[0]-P(4)[0])*Math.sin(roll)+(gap[1]-P(4)[1])*Math.cos(roll)
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){
    const i=y*w+x,dx=x+.5-P(4)[0],dy=y+.5-P(4)[1]
    const across=dx*Math.cos(roll)+dy*Math.sin(roll),below=-dx*Math.sin(roll)+dy*Math.cos(roll)
    const lowerLimit=dist(P(4),P(1))+noseW*.04
    const underFade=smooth((lowerLimit-below)/(noseW*.04))
    // 코밑 중앙만 막는다. 콧망울 바깥은 코끝보다 아래에 있어도 지우지 않는다.
    const centerProtection=1-smooth((Math.abs(across)/noseW-.16)/.19)
    const geometry=1-centerProtection*(1-underFade)
    // 실제 어두운 콧구멍은 더 칠하지 않고, 그 바깥의 피부 음영만 남긴다.
    const p=i*4,luma=data[p]*.299+data[p+1]*.587+data[p+2]*.114
    const nostrilFade=below>-noseW*.05?smooth((luma/noseSkin-.45)/.30):1
    // ref4/ref5의 분절: 콧대 중간을 실제로 비워 긴 두 줄이 코끝까지 이어지지 않게 한다.
    const bridgeBreak=smooth((Math.abs(below-gapY)-noseW*.04)/(noseW*.055))
    // 곧은 콧대 맞춤은 끊지 않음
    for(const mask of noseMasks)mask[i]*=noseFeather[i]*geometry*nostrilFade*(mask===noseCorrection&&fit?.nose==='straight'?1:bridgeBreak)
    noseAccent[i]*=noseFeather[i]*geometry*nostrilFade
  }
  // 코끝 홈도 4→1 사이 실제 축에서만 배치한다.
  const tipPoint=(x:number,y:number):Pt=>{
    const c=lerp(P(4),P(1),y)
    return [c[0]+noseW*x*Math.cos(roll),c[1]+noseW*x*Math.sin(roll)]
  }
  // T존 (남성): 이마 가운데 세로·가는 콧대·턱끝, 인중 위·광대는 비움
  const tzone = new Float32Array(n)
  stampFan(tzone, w, h, P(9), P(151), faceW, roll, 0.6 * (1 - .8 * longFace))
  for (let t = 0; t <= 1; t += 1 / 9) stamp(tzone, w, h, lerp(P(168), P(195), t), faceW * 0.01 * (1 - 0.3 * shape.wideNose), faceW * 0.016, roll, 0.85)
  // 턱끝: 가운데를 비우고 양쪽 볼록한 곳에 둘로 (엉덩이턱 음영과 짝)
  const chinC = lerp(P(17), P(152), 0.55)
  for (const dir of [-1, 1]) stamp(tzone, w, h, [chinC[0] + dir * faceW * 0.035 * Math.cos(roll), chinC[1] + dir * faceW * 0.035 * Math.sin(roll)], faceW * 0.022, faceW * 0.02, roll, 0.6 * (1 - .8 * longFace))
  // 엉덩이코: 코끝 가운데 아주 가는 세로 음영 + 코끝 양쪽 둥근 하이라이트 둘
  const noseCleft = new Float32Array(n), noseCleftHL = new Float32Array(n), tipW = noseW
  // 짧고 가는 코끝 홈. 콧대부터 이어 그리면 검은 세로선이 되므로 코끝 안에서만 그린다.
  for (let t=0;t<=1;t+=.2) stamp(noseCleft,w,h,tipPoint(0,.05+.28*t),noseW*.032,noseW*.055,roll,.95*Math.sin(Math.PI*(.15+.7*t)))
  for (const dir of [-1,1]) stamp(noseCleftHL,w,h,tipPoint(dir*.08,.12),tipW*.07,tipW*.08,roll,.85)
  // 턱끝 홈도 턱 중앙의 짧은 구간에만. 양옆의 작은 밝은 면으로 입체감을 만든다.
  const chinCleft = new Float32Array(n), chinCleftHL = new Float32Array(n)
  for (let t=0;t<=1;t+=.2) stamp(chinCleft,w,h,lerp(P(17),P(152),.61+.13*t),faceW*.0045,faceW*.008,roll,.85*Math.sin(Math.PI*(.15+.7*t)))
  const cleftCenter=lerp(P(17),P(152),.67)
  for (const dir of [-1,1]) stamp(chinCleftHL,w,h,[cleftCenter[0]+dir*faceW*.017*Math.cos(roll),cleftCenter[1]+dir*faceW*.017*Math.sin(roll)],faceW*.012,faceW*.013,roll,.65)
  // 하이라이터: 콧대(콧볼이 넓으면 가늘게), 인중 위, 턱 끝
  const bridgeW = faceW * 0.018 * (1 - 0.45 * shape.wideNose)
  for (let t = 0; t <= 1; t += 1 / 7) stamp(centerHighlight, w, h, lerp(P(168), P(195), t), bridgeW, faceW * 0.018, 0, 0.9)
  // 코끝: 들창코는 코끝 아래쪽까지 이어 길어 보이게, 화살코는 코끝 위쪽에 작은 점으로 올려 보이게
  for (const m of [centerHighlight, featHL]) {
    if (shape.upturned > 0) stamp(m, w, h, P(4), bridgeW, faceW * 0.016, roll, 0.9 * shape.upturned)
    if (shape.drooping > 0) stamp(m, w, h, lerp(P(195), P(4), 0.45), bridgeW * 0.9, faceW * 0.012, roll, 0.9 * shape.drooping)
  }
  stamp(centerHighlight, w, h, lerp(P(0), P(164), 0.55), faceW * 0.02, faceW * 0.012, roll, 0.7)
  stamp(centerHighlight, w, h, lerp(P(17), P(152), 0.55), faceW * 0.035, faceW * 0.025, roll, 0.6)
  for (let i = 0; i < n; i++) highlight[i] = Math.max(cheekHighlight[i], centerHighlight[i])
  // 광대+코끝 / 광대+턱끝
  const cheekNose = cheekHighlight.slice(), cheekChin = cheekHighlight.slice()
  stamp(cheekNose, w, h, lerp(P(4), P(1), 0.3), faceW * 0.022, faceW * 0.02, roll, 0.8)
  stamp(cheekChin, w, h, lerp(P(17), P(152), 0.55), faceW * 0.035, faceW * 0.025, roll, 0.7)
  // 블러셔 광: 원본에서 주변보다 밝은 픽셀일수록 광이 강하게 맺힌다 (피부 입체를 따라감).
  const luma = new Float32Array(n)
  for (let i = 0, p = 0; i < n; i++, p += 4) luma[i] = (data[p] * .299 + data[p + 1] * .587 + data[p + 2] * .114) / 255
  const localLuma = blur(luma, w, h, Math.max(2, faceW * 0.04))
  const cheekGlow = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const rel = Math.min(1, Math.max(0, .5 + (luma[i] - localLuma[i]) * 7))
    cheekGlow[i] = glowZone[i] * (.12 + .88 * rel * rel * (3 - 2 * rel))
  }
  // 숙취: 콧등 가로 연결 / 울먹: 코끝
  stamp(blushHangover, w, h, P(195), faceW * 0.06, faceW * 0.03, roll, 0.6)
  stamp(blushTeary, w, h, lerp(P(4), P(1), 0.5), faceW * 0.035, faceW * 0.03, roll, 0.6)
  // 선번: 광대 위쪽(눈 밑 바깥)에서 콧등 가운데를 가로질러 반대편까지 이어지는 띠
  const blushSunburn = new Float32Array(n)
  for (const side of SIDES) {
    const cheekTop = lerp(lerp(P(side.under), P(side.apple), 0.35), P(side.upper), 0.2)
    for (let t = 0; t <= 1; t += 1 / 6) stamp(blushSunburn, w, h, lerp(cheekTop, lerp(P(168), P(195), 0.55), t), faceW * 0.05, faceW * 0.03, roll, 0.85 - 0.15 * t)
  }
  stamp(blushSunburn, w, h, lerp(P(168), P(195), 0.55), faceW * 0.035, faceW * 0.022, roll, 0.75)
  // 코끝만 (다른 블러셔에 더함)
  const blushNose = new Float32Array(n)
  stamp(blushNose, w, h, lerp(P(4), P(1), 0.5), faceW * 0.04, faceW * 0.034, roll, 0.8)
  // 나른한: 코끝·턱끝 살짝 / 중안부 짧게: 코끝
  stamp(blushEnnui, w, h, lerp(P(4), P(1), 0.5), faceW * 0.035, faceW * 0.03, roll, .55)
  stamp(blushEnnui, w, h, lerp(P(17), P(152), .6), faceW * 0.045, faceW * 0.025, roll, .45)
  stamp(blushMid, w, h, lerp(P(4), P(1), 0.5), faceW * 0.035, faceW * 0.03, roll, .6)
  // 블러셔 외곽: 타원을 겹친 그대로면 진하게 올릴 때 가운데가 평평하게 차고 가장자리가 뚝 끊겨 도장처럼 보임
  // → 넓게 한 번 흐린 뒤 원래 최대값에 맞추고, 거듭제곱으로 가운데부터 서서히 옅어지게
  for (const m of [blush, blushWide, blushDiagonal, blushUnder, blushHangover, blushTeary, blushNose, blushSunburn, blushSlim, blushEnnui, blushMid]) {
    let peak = 0
    for (let i = 0; i < n; i++) if (m[i] > peak) peak = m[i]
    const soft = blur(m, w, h, faceW * BLUSH_FEATHER)
    let softPeak = 0
    for (let i = 0; i < n; i++) if (soft[i] > softPeak) softPeak = soft[i]
    const k = softPeak > 0 ? peak / softPeak : 0
    // 흐림 누적합 오차로 아주 작은 음수가 나오면 거듭제곱이 NaN → 검은 줄, 0~1로 자름
    const norm = k / Math.max(peak, 1e-6)
    for (let i = 0; i < n; i++) { const v = soft[i] * norm; m[i] = v > 1e-4 ? peak * Math.pow(Math.min(1, v), BLUSH_FALLOFF) : 0 }
  }
  for (let i=0;i<n;i++) boneHighlight[i]=Math.max(boneHighlight[i],tzone[i]*.65)
  for (const m of [noseAccent, boneHighlight, chinCleftHL, noseCorrection, noseShading, noseSlim, noseTip, noseSculpted, noseVTip, noseWings, tzone, chinCleft, noseCleft, noseCleftHL, featShade, featHL, cheekHighlight, centerHighlight, shading, jawV, jawChin, sculpt, highlight, cheekNose, cheekChin, blush, blushWide, blushDiagonal, blushUnder, blushHangover, blushTeary, blushNose, blushSunburn, blushSlim, blushEnnui, blushMid, cheekGlow, shadowBasic, shadowWing, shadowSmoky, shadowLong, underOuter, underFull, underWide, lidShine, aegyoLight, aegyoShadow, aegyoLong, aegyoLongShadow]) {
    clip(m)
    // 흐림 때문에 눈/치아에 색이 새지 않게 눈 다각형 내부는 정확히 0.
    for (let i = 0; i < n; i++) if (eyeHard[i]) m[i] = 0
  }

  // 립: 바깥 입술 - 안쪽(벌린 입), 경계만 살짝 흐림
  // 다문 입은 안쪽 다각형이 윗·아랫입술 사이 1px 선이라 그대로 빼면 그 선만 안 칠해져 점선이 남음
  // → 입이 실제로 벌어졌을 때(입 너비의 4% 이상)만 안쪽을 뺌
  const mouthOpen = dist(P(13), P(14)) > dist(P(61), P(291)) * 0.04
  const lipHard = new Float32Array(n)
  fillPolygon(lipHard, w, h, LIPS_OUTER.map(P), 1)
  if (mouthOpen) fillPolygon(lipHard, w, h, LIPS_INNER.map(P), 0)
  const lip = blur(lipHard, w, h, Math.max(1, faceW * 0.004))
  const mouthOpening = new Float32Array(n)
  if (mouthOpen) fillPolygon(mouthOpening, w, h, LIPS_INNER.map(P), 1)
  // 블러립: 윤곽을 넓게 흐려 경계 밖으로 살짝 번지게 (오버라인)
  const lipSoft = blur(lipHard, w, h, Math.max(1.5, faceW * 0.012))
  const gradient = new Float32Array(n), lipBlur = new Float32Array(n), gloss = new Float32Array(n)
  const seamA = P(13), seamB = P(14), upperLip = P(0), lowerLip = P(17)
  const lipCenter = lerp(seamA, seamB, 0.5)
  const mouthWidth = dist(P(61), P(291))
  const mouthAngle = Math.atan2(P(291)[1] - P(61)[1], P(291)[0] - P(61)[0])
  const cosM = Math.cos(mouthAngle), sinM = Math.sin(mouthAngle)
  const thickness = Math.max(2, dist(upperLip, lowerLip) / 2)
  // 글로시 광: 아랫입술 가운데 넓고 옅은 윤기 + 양옆·윗입술에 더 옅게, 넓게 흐려 반투명하게
  // (작고 또렷한 흰 점 여러 개는 물집처럼 보임, 넓은 띠 하나는 하얀 줄처럼 보임)
  const glossCore = new Float32Array(n)
  const lowerSpot = lerp(seamB, lowerLip, 0.42), upperSpot = lerp(upperLip, seamA, 0.45)
  const spotH = Math.max(thickness * 0.3, mouthWidth * 0.03)
  for (const [t, size, weight] of [[0, 1, 1], [-.28, .7, .55], [.28, .7, .55]] as const) {
    const side = lerp(lowerSpot, t < 0 ? P(61) : P(291), Math.abs(t))
    stamp(glossCore, w, h, side, mouthWidth * 0.09 * size, spotH * size, mouthAngle, weight)
  }
  stamp(glossCore, w, h, upperSpot, mouthWidth * 0.06, spotH * 0.6, mouthAngle, 0.35)
  const glossSoft = blur(glossCore, w, h, Math.max(1, thickness * 0.25))
  for (let i = 0; i < n; i++) gloss[i] = Math.min(1, glossSoft[i])
  for (let i = 0; i < n; i++) {
    // 뿌연 입술 경계도 입 안과 얼굴 바깥으로는 번지지 않게 고정.
    lip[i] *= ovalHard[i] * (1 - mouthOpening[i])
    const x = i % w + 0.5 - lipCenter[0], y = Math.floor(i / w) + 0.5 - lipCenter[1]
    const vertical = Math.abs(-x * sinM + y * cosM) / thickness
    const horizontal = Math.abs(x * cosM + y * sinM) / Math.max(1, mouthWidth * 0.5)
    gradient[i] = lip[i] * (.02 + .98 * Math.exp(-3.2 * vertical * vertical)) * Math.max(.05, 1 - .95 * horizontal * horizontal)
    lipBlur[i] = Math.min(1, lipSoft[i] * 1.15) * (1 - mouthOpening[i]) * ovalHard[i] * (.3 + .7 * Math.exp(-.8*vertical*vertical)) * Math.max(.45,1-.4*horizontal*horizontal)
    gloss[i] *= lip[i]
  }
  let sw = 0, sv = 0
  for (let i = 0, p = 0; i < n; i++, p += 4) {
    if (lipHard[i] > 0) { sw++; sv += Math.max(data[p], data[p + 1], data[p + 2]) / 255 }
  }
  // 입술 내부의 주변 명도와 비교해 반사광만 분리한다. 밝은 입술 전체를 광택으로 보지 않는다.
  const lipLight = new Float32Array(n)
  for (let i=0,p=0;i<n;i++,p+=4) lipLight[i]=Math.max(data[p],data[p+1],data[p+2])/255*lipHard[i]
  const support = blur(lipHard,w,h,Math.max(1,mouthWidth*.12))
  const localLight = blur(lipLight,w,h,Math.max(1,mouthWidth*.12))
  const lipSpecular = new Float32Array(n)
  let shineSum=0,shineWeight=0
  for (let i=0,p=0;i<n;i++,p+=4) {
    if (lipHard[i]===0) continue
    const [ ,sat,v]=rgbToHsv(data[p],data[p+1],data[p+2])
    const baseline=localLight[i]/Math.max(.001,support[i])
    const excess=Math.max(0,v-baseline-.035)
    // 주변보다 밝고 하얗게 뜬 반사를 우선 처리하고 작은 입술 굴곡은 남긴다.
    const confidence=Math.min(1,excess/.10)*(.55+.45*(1-sat))
    lipSpecular[i]=excess*confidence
    shineSum+=lipSpecular[i];shineWeight++
  }
  const lipShine=Math.min(1,shineSum/Math.max(1,shineWeight)*45)
  const lipRel = new Float32Array(n)
  for (let i=0;i<n;i++) if (lipHard[i]>0) lipRel[i]=Math.min(1,Math.max(0,.5+(lipLight[i]-localLight[i]/Math.max(.001,support[i]))*6))
  // 피부 보정 준비: 얼굴 안에서 눈(넓게)·눈썹·입술·콧구멍 쪽 제외, 경계는 부드럽게
  const skinHard = ovalHard.slice()
  const holes = new Float32Array(n)
  fillPolygon(holes, w, h, LEFT_EYE.map(P), 1); fillPolygon(holes, w, h, RIGHT_EYE.map(P), 1)
  for (const brow of [[70, 63, 105, 66, 107, 55, 65, 52, 53, 46], [336, 296, 334, 293, 300, 276, 283, 282, 295, 285]]) fillPolygon(holes, w, h, brow.map(P), 1)
  fillPolygon(holes, w, h, LIPS_OUTER.map(P), 1)
  const holesSoft = blur(holes, w, h, faceW * 0.012)
  const skinMask = new Float32Array(n)
  for (let i = 0; i < n; i++) skinMask[i] = oval[i] * Math.max(0, 1 - holesSoft[i] * 2.2) * skinHard[i]
  const skinMaskSoft = blur(skinMask, w, h, faceW * 0.008)
  // 결 정리: 채널별 guided filter (반경 얼굴 너비 1.2%, 잔결만 흐려지게 eps 작게)
  const chans = [0, 1, 2].map(c => { const a = new Float32Array(n); for (let i = 0, p = c; i < n; i++, p += 4) a[i] = data[p] / 255; return a })
  const sm = chans.map(ch => guidedSmooth(ch, w, h, Math.max(2, Math.round(faceW * 0.012)), 0.0016))
  const skinSmooth = new Uint8ClampedArray(n * 3)
  for (let i = 0; i < n; i++) for (let c = 0; c < 3; c++) skinSmooth[i * 3 + c] = sm[c][i] * 255
  // 피부 평균색과 넓게 흐린 a·b (붉은기·얼룩 = 평균보다 a가 높은 곳)
  const La = new Float32Array(n), Lb = new Float32Array(n), Ll = new Float32Array(n)
  let sL = 0, sA = 0, sB = 0, sW = 0
  for (let i = 0, p = 0; i < n; i++, p += 4) {
    if (skinMaskSoft[i] < 0.05) continue
    const [L, a, b] = toLab(data[p], data[p + 1], data[p + 2])
    La[i] = a; Lb[i] = b; Ll[i] = L
    if (skinMaskSoft[i] > 0.6) { sL += L; sA += a; sB += b; sW++ }
  }
  const skinMean: [number, number, number] = sW ? [sL / sW, sA / sW, sB / sW] : [70, 10, 15]
  for (let i = 0; i < n; i++) if (skinMaskSoft[i] < 0.05) { La[i] = skinMean[1]; Lb[i] = skinMean[2] }
  const skinLowA = blur(La, w, h, faceW * 0.03), skinLowB = blur(Lb, w, h, faceW * 0.03)
  // 볼 집중 보정 자리: 트러블 메우기와 같은 볼 원, 코 주변 제외, 경계 부드럽게
  const cheekRaw = new Float32Array(n), cheekCs = [P(50), P(280)], cheekNosePts = [98, 327, 2, 94, 164, 64, 294, 4, 5].map(P)
  const cheekR = faceW * CHEEK_RADIUS, cheekNoseR = faceW * CHEEK_NOSE_R
  for (let i = 0; i < n; i++) {
    if (skinMaskSoft[i] < .05) continue
    const x = i % w, y = (i / w) | 0
    let c = 0
    for (const [cx, cy] of cheekCs) { const d = Math.hypot(x - cx, y - cy) / cheekR; if (d < 1) c = Math.max(c, d < .6 ? 1 : (1 - d) / .4) }
    if (!c) continue
    let nd = Infinity
    for (const [nx, ny] of cheekNosePts) nd = Math.min(nd, Math.hypot(x - nx, y - ny) / cheekNoseR)
    cheekRaw[i] = c * Math.min(1, Math.max(0, nd - 1))
  }
  const skinCheek = blur(cheekRaw, w, h, faceW * .02)
  // 수염 자국: 코 밑부터 턱 아래까지 얼굴 안(입술 제외)에서, 볼 앞쪽 피부보다 어둡고(L) 푸르스름하거나 잿빛(b 낮음)인 정도
  // 픽셀마다 잡으면 모공·털 하나하나가 얼룩져 보여 넓게 흐린 값으로 (면도 자국은 넓게 번진 그늘)
  const sampleLab = (pt: Pt, r: number) => {
    let L = 0, A = 0, B = 0, c = 0
    for (let y = Math.max(0, Math.round(pt[1] - r)); y <= Math.min(h - 1, Math.round(pt[1] + r)); y++) for (let x = Math.max(0, Math.round(pt[0] - r)); x <= Math.min(w - 1, Math.round(pt[0] + r)); x++) {
      const o = (y * w + x) * 4, [l, a, b] = toLab(data[o], data[o + 1], data[o + 2]); L += l; A += a; B += b; c++
    }
    return [L / c, A / c, B / c] as [number, number, number]
  }
  const refs = [50, 280, 101, 330].map(id => sampleLab(P(id), faceW * 0.025))
  const beardRef = [0, 1, 2].map(k => refs.reduce((sum, r) => sum + r[k], 0) / refs.length) as [number, number, number]
  const lipNear = blur(lipHard, w, h, faceW * 0.012), mouthC = lerp(P(13), P(14), .5), noseY = P(2)[1]
  const beardRaw = new Float32Array(n)
  for (let i = 0, p = 0; i < n; i++, p += 4) {
    if (!ovalHard[i] || lipNear[i] > .15) continue
    const x = i % w, y = (i / w) | 0
    const top = Math.min(1, Math.max(0, (y - noseY) / (faceW * .04))), dMouth = Math.hypot(x - mouthC[0], y - mouthC[1]) / (faceW * .42)
    if (top <= 0 || dMouth >= 1) continue
    const [L, a, b] = toLab(data[p], data[p + 1], data[p + 2])
    const shadow = Math.max(0, (beardRef[0] - L) * .6 + (beardRef[2] - b) * 1.0 + (beardRef[1] - a) * .3 - BEARD_MIN) / BEARD_RANGE
    beardRaw[i] = Math.min(1, shadow) * top * Math.min(1, (1 - dMouth) / .25)
  }
  const beardMask = blur(beardRaw, w, h, Math.max(1, faceW * 0.01))
  const { spotMask, spotFill } = findSpots(data, w, h, faceW, skinMaskSoft, Ll, La, [98, 327, 2, 94, 164, 64, 294].map(P), [50, 280].map(P))
  return {
    browFill: ownBrowFill(data, w, h, P, faceW),
    noseFit: Boolean(fit), beardMask, beardRef, spotMask, spotFill, nosePalette: sampleNosePalette(image,points.map(point=>[point[0]*w,point[1]*h] as Pt)), noseAccent: blur(noseAccent,w,h,Math.max(.5,noseW*.018)), chinCleftHL: blur(chinCleftHL,w,h,Math.max(1,faceW*.003)), noseCorrection: blur(noseCorrection,w,h,Math.max(1,faceW*.004)), featShade: blur(featShade, w, h, Math.max(1, faceW * 0.008)), featHL: blur(featHL, w, h, Math.max(1, faceW * 0.008)), chinCleft: blur(chinCleft, w, h, Math.max(1, faceW * 0.006)), noseCleft: blur(noseCleft, w, h, Math.max(1, faceW * 0.003)), noseCleftHL: blur(noseCleftHL, w, h, Math.max(1, faceW * 0.004)),
    shadingSoft: Object.fromEntries(([['natural', shading], ['vline', jawV], ['chin', jawChin], ['sculpt', sculpt]] as const).map(([k, m]) => {
      const soft = blur(m, w, h, faceW * 0.025)
      for (let i = 0; i < n; i++) soft[i] = Math.min(1, soft[i] * 1.15) * ovalHard[i]
      return [k, soft]
    })) as Record<MakeupShapes['shading'], Float32Array>,
    skinMask: skinMaskSoft, skinSmooth, skinLowA, skinLowB, skinMean, skinCheek,
    width: w, height: h, src: data, points: points.map(point => [point[0] * w, point[1] * h] as Pt), lipGloss: gloss,
    variants: {
      skin: { cushion: skinMask },
      shading: { natural: shading, vline: jawV, chin: jawChin, sculpt }, noseShading: { soft: noseShading, slim: noseSlim, tip: noseTip, sculpted: noseSculpted, vtip: noseVTip, wings: noseWings }, highlight: { standard: highlight, center: centerHighlight, cheek: cheekHighlight, cheekNose, cheekChin, tzone, bone: boneHighlight },
      blush: { round: blush, wide: blushWide, diagonal: blushDiagonal, undereye: blushUnder, hangover: blushHangover, teary: blushTeary, sunburn: blushSunburn, slim: blushSlim, ennui: blushEnnui, midface: blushMid },
      eyeshadow: { basic: shadowBasic, wing: shadowWing, smoky: shadowSmoky, long: shadowLong },
      shadowPoint: { wing: shadowWing, long: shadowLong, smoky: shadowSmoky },
      underShadow: { outer: underOuter, full: underFull, wide: underWide },
      aegyo: { soft: aegyoLight, long: aegyoLong },
      eyeliner: { basic: linerBasic, wing: linerWing, down: linerDown, longWing: linerLongWing, longDown: linerLongDown },
      lip: { glossy: lip, gradient, blur: lipBlur },
    }, lipMeanV: sw ? sv / sw : 0.5, lipSpecular, lipShine, lipRel, blushNose, lidShine, aegyoShadow: { soft: aegyoShadow, long: aegyoLongShadow }, upperLid, lashStart, cheekGlow,
  }
}

// 색상각(도) 사이를 짧은 쪽으로 섞음
function mixHue(a: number, b: number, t: number) {
  let d = b - a
  if (d > 180) d -= 360
  if (d < -180) d += 360
  return (a + d * t + 360) % 360
}

// 사용자 눈매(속눈썹 라인)에 맞춘 진하기 배율 (속눈썹·아이라인 공통): 윗눈꺼풀 바로 위 띠에서 콧대 피부의 45%보다 어두운 픽셀 비율 r 기준
// 생얼 연한 속눈썹 .2 안팎 → 연하게(.6), 보통·짙은 속눈썹 .3~.45 → 그대로, 화장한 진한 속눈썹 .55+ → 겹쳐 과해지지 않게 다시 연하게
// 입술 창백한 정도 (0~1): 입술과 볼 피부의 붉은기(a*) 차이가 LIP_PALE_DIFF보다 작을수록 1에 가까움 (테스트 13장 차이 11~22, 가장 옅은 사진 10.7)
const LIP_PALE_DIFF = 16, LIP_PALE_RANGE = 8
const lipPaleCache = new WeakMap<PreparedFace, number>()
export function lipPaleness(face: PreparedFace) {
  const cached = lipPaleCache.get(face)
  if (cached !== undefined) return cached
  const { src, skinMask } = face, lip = face.variants.lip.glossy
  let la = 0, lc = 0, sa = 0, sc = 0
  for (let i = 0, p = 0; i < lip.length; i++, p += 4) {
    if (lip[i] > .9) { la += toLab(src[p], src[p + 1], src[p + 2])[1]; lc++ }
    else if (skinMask[i] > .9 && (i & 7) === 0) { sa += toLab(src[p], src[p + 1], src[p + 2])[1]; sc++ }
  }
  const value = lc && sc ? Math.min(1, Math.max(0, (LIP_PALE_DIFF - (la / lc - sa / sc)) / LIP_PALE_RANGE)) : 0
  lipPaleCache.set(face, value)
  return value
}
const lashLineCache = new WeakMap<PreparedFace, number>()
const LASH_LINE_IDS = [[33, 246, 161, 160, 159, 158, 157, 173, 133], [362, 398, 384, 385, 386, 387, 388, 466, 263]]
export function lashLineMatch(face: PreparedFace) {
  const cached = lashLineCache.get(face)
  if (cached !== undefined) return cached
  const { width: w, height: h, src, points } = face
  const luma = (x: number, y: number) => {
    const px = Math.round(x), py = Math.round(y)
    if (px < 0 || py < 0 || px >= w || py >= h) return 255
    const o = (py * w + px) * 4; return src[o] * .299 + src[o + 1] * .587 + src[o + 2] * .114
  }
  const skin = luma(points[6][0], points[6][1])
  let dark = 0, total = 0
  for (const ids of LASH_LINE_IDS) {
    const eyeW = Math.hypot(points[ids[ids.length - 1]][0] - points[ids[0]][0], points[ids[ids.length - 1]][1] - points[ids[0]][1])
    for (let k = 1; k < ids.length - 1; k++) {
      const [x, y] = points[ids[k]], [ax, ay] = points[ids[k - 1]], [bx, by] = points[ids[k + 1]]
      let nx = by - ay, ny = -(bx - ax)
      const len = Math.hypot(nx, ny) || 1
      nx /= len; ny /= len
      if (ny > 0) { nx = -nx; ny = -ny }
      for (let t = eyeW * .02; t < eyeW * .12; t += .5) { total++; if (luma(x + nx * t, y + ny * t) < skin * .45) dark++ }
    }
  }
  const ss = (t: number) => { const c = Math.min(1, Math.max(0, t)); return c * c * (3 - 2 * c) }
  const r = total ? dark / total : .3
  const value = (.5 + .5 * ss((r - .15) / .2)) * (1 - .5 * ss((r - .45) / .2))
  lashLineCache.set(face, value)
  return value
}

// 내 눈썹 채우기 최대 진하기 (농도 1일 때 틈 자리에서 눈썹 색 쪽으로 옮기는 비율)
const BROW_OWN_K = .75
// browFill: 에셋 없이 내 눈썹 빈 곳만 채움 (amount 0이면 안 함)
export function renderMakeup(face: PreparedFace, s: MakeupSettings, out: Uint8ClampedArray, browFill?: { amount: number; hex: string }) {
  out.set(face.src)
  const { variants } = face
  const n = face.width * face.height
  const tmp = [0, 0, 0]
  const active = (part: MakeupPart) => s[part].on && s[part].amount > 0

  // 피부 보정(쿠션): 다른 메이크업보다 먼저
  // 1) 결 정리: guided filter 결과 쪽으로 섞음  2) 붉은기·얼룩 완화: 넓게 흐린 a·b가 평균보다 튄 만큼 되돌림
  // 3) 쿠션 색 쪽으로 톤 맞춤: 피부 평균 → 쿠션 색 차이만큼 옮김 (명암은 그대로)
  if (active('skin')) {
    const k = Math.min(1, s.skin.amount), [cr, cg, cb] = hexToRgb(s.skin.hex), [tL, tA, tB] = toLab(cr, cg, cb)
    const [mL, mA, mB] = face.skinMean, lab3 = [0, 0, 0]
    for (let i = 0, p = 0; i < n; i++, p += 4) {
      const m = face.skinMask[i] * k
      if (m < 0.003) continue
      // 수염 자국 가리기 (컨실러처럼 볼 피부색 쪽으로, 결 정리 전에)
      const beard = face.beardMask[i] * (s.skin.beard ?? 0) * Math.min(1, k * 1.6)
      if (beard > .01) {
        const [L0, a0, b0] = toLab(out[p], out[p + 1], out[p + 2]), [rL, rA, rB] = face.beardRef
        fromLab(L0 + Math.max(0, rL - L0) * beard * BEARD_L, a0 + (rA - a0) * beard * BEARD_AB, b0 + (rB - b0) * beard * BEARD_AB, lab3)
        out[p] = lab3[0]; out[p + 1] = lab3[1]; out[p + 2] = lab3[2]
      }
      // 트러블 메우기 (피부 보정 강도를 따라감, 결 정리 전에)
      const spot = Math.min(1, face.spotMask[i] * Math.min(1, k * SKIN_SPOT))
      if (spot > .01) for (let c = 0; c < 3; c++) out[p + c] += (face.spotFill[i * 3 + c] - out[p + c]) * spot
      const ch = face.skinCheek[i]
      const sm = Math.min(.95, SKIN_SMOOTH * m * (1 + CHEEK_SMOOTH * ch)), even = SKIN_EVEN * m * (1 + CHEEK_EVEN * ch)
      const r = out[p] + (face.skinSmooth[i * 3] - out[p]) * sm, g = out[p + 1] + (face.skinSmooth[i * 3 + 1] - out[p + 1]) * sm, b = out[p + 2] + (face.skinSmooth[i * 3 + 2] - out[p + 2]) * sm
      let [L, a, bb] = toLab(r, g, b)
      const a0 = a, b0 = bb
      a -= (face.skinLowA[i] - mA) * even
      bb -= (face.skinLowB[i] - mB) * even * .6
      // 밝기는 톤업 쪽으로만 (예전엔 -2까지 허용해 아주 밝은 피부가 어두워졌음), 색감(a·b)은 쿠션 쪽으로
      // 피부가 쿠션보다 밝으면 색 옮기는 양을 줄이고, 색을 더하는 쪽(노란·붉은 기 증가)은 절반만 (옅은 피부에 색이 얹히면 칙칙해 보임)
      L += Math.min(4, Math.max(0, (tL - mL) * SKIN_TONE * .6 + 1.5)) * m
      const pull = SKIN_TONE * m * (mL > tL ? Math.max(SKIN_BRIGHT_PULL, 1 - (mL - tL) / 12) : 1)
      a += (tA - mA) * pull * (tA > mA ? .5 : 1); bb += (tB - mB) * pull * (tB > mB ? .5 : 1)
      fromLab(L, a, bb, lab3)
      // 아주 밝은 피부는 빨강 채널이 255 근처라 색을 더하면 잘려 오히려 어두워짐 → 들어갈 때까지 색 변화만 줄임 (밝기 유지)
      for (let t = .5; t > .05 && Math.max(lab3[0], lab3[1], lab3[2]) > 255; t *= .5) fromLab(L, a0 + (a - a0) * t, b0 + (bb - b0) * t, lab3)
      out[p] = lab3[0]; out[p + 1] = lab3[1]; out[p + 2] = lab3[2]
    }
  }
  // 내 눈썹 빈 곳: 눈썹 색 쪽으로 옮기되 원래보다 밝아지지 않게 (이미 진한 털은 그대로)
  if (browFill && browFill.amount > 0 && face.browFill) {
    const [br, bg, bb] = hexToRgb(browFill.hex), k = Math.min(1, browFill.amount) * BROW_OWN_K, col = [br, bg, bb]
    for (let i = 0, p = 0; i < n; i++, p += 4) {
      const f = face.browFill[i] * k
      if (f < .003) continue
      for (let c = 0; c < 3; c++) out[p + c] = Math.min(out[p + c], out[p + c] + (col[c] - out[p + c]) * f)
    }
  }
  // 쉐딩: 쉐딩 색으로 곱하기 (어둡게)
  // 쉐딩: 정해 둔 쉐딩 색을 곱하지 않고 그 자리 피부색을 그대로 어둡게 (색이 피부 위에 얹혀 보이면 얼룩·띠처럼 부자연스러움)
  // 밝기만 내리고 채도를 살짝 올려 그늘진 피부색처럼, 마스크는 넓게 흐린 값이라 경계 없이 그라데이션
  const shade = (mask: Float32Array, k: number, palette?: NosePalette) => {
    const lab = [0, 0, 0]
    for (let i = 0, p = 0; i < n; i++, p += 4) {
      const a = mask[i] * k
      if (a < 0.002) continue
      const [L, A, B] = toLab(out[p], out[p + 1], out[p + 2])
      if(palette){
        // 원래 어두운 옆면은 덜 누른다. 피부결은 유지하고 샘플에서 얻은 색 차이만 더한다.
        const room=Math.max(.25,Math.min(1,(L-palette.shadow[0]+2)/Math.max(1,palette.depth)))
        const amount=a*room
        fromLab(L-palette.depth*amount,A+palette.chroma[0]*amount*.65,B+palette.chroma[1]*amount*.65,lab)
      }else fromLab(L - SHADE_DEPTH * a, A * (1 + .12 * a), B * (1 + .2 * a), lab)
      out[p] = lab[0]; out[p + 1] = lab[1]; out[p + 2] = lab[2]
    }
  }
  if (active('shading')) {
    shade(face.shadingSoft[s.shading.shape], s.shading.amount)
    if (s.shading.cleft) shade(face.chinCleft, s.shading.cleft * Math.min(1, s.shading.amount * 2))
  }
  // 얼굴형·광대 보정은 턱 쉐딩 강도, 코 보정은 코 쉐딩 강도를 따른다.
  const contour = active('shading') ? s.shading.amount : 0
  if (contour > 0) shade(face.featShade, Math.min(1, contour * FEAT_SHADE))
  if (active('noseShading')) {
    const style=variants.noseShading[s.noseShading.shape], mask=new Float32Array(n)
    // 코 맞춤 층은 옅은 룩에서도 보이게 바닥값(FIT_NOSE_MIN)을 둠
    const fitK = face.noseFit ? Math.max(FIT_NOSE * s.noseShading.amount * .8, FIT_NOSE_MIN * Math.min(1, s.noseShading.amount * 10)) : s.noseShading.amount * .8
    for(let i=0;i<n;i++) mask[i]=Math.max(style[i]*s.noseShading.amount*.8,Math.min(1,face.noseCorrection[i]*fitK))
    shade(mask, 1,face.nosePalette)
    if (s.noseShading.noseCleft) shade(face.noseCleft, s.noseShading.noseCleft * Math.min(1, s.noseShading.amount * 2),face.nosePalette)
  }
  // 하이라이터: 스크린 (밝게)
  if (active('highlight')) {
    const [r, g, b] = hexToRgb(s.highlight.hex), k = s.highlight.amount * 0.45, m = variants.highlight[s.highlight.shape]
    // 엉덩이코: 코끝 양쪽 둥근 하이라이트 (코 쉐딩의 엉덩이코 음영과 짝)
    const nc = active('noseShading') ? (s.noseShading.noseCleft ?? 0) * Math.min(1,s.noseShading.amount*2) : 0
    const cc = active('shading') ? (s.shading.cleft ?? 0) * Math.min(1,s.shading.amount*2) : 0
    // 피부색 기반: 그 자리 피부를 Lab에서 밝히고 채도를 살짝 빼서 빛 받은 피부처럼, 하이라이터 색은 색감만 조금 (흰색을 덮으면 회색·분칠처럼 뜸)
    const [, hA, hB] = toLab(r, g, b), lab = [0, 0, 0]
    for (let i = 0, p = 0; i < n; i++, p += 4) {
      const a = Math.min(1, Math.max(m[i] * k, face.noseCleftHL[i] * nc * k * 1.5, face.chinCleftHL[i] * cc * k * 1.2, face.featHL[i] * k * FEAT_HL, active('noseShading') ? face.noseAccent[i]*k*Math.min(1,s.noseShading.amount*2)*1.4 : 0))
      if (a < 0.002) continue
      const [L, A, B] = toLab(out[p], out[p + 1], out[p + 2])
      const keep = 1 - HL_CHROMA * a, tint = HL_TINT * a
      fromLab(L + HL_LIFT * a * Math.max(0, 1 - L / 105), A * keep + (hA - A * keep) * tint, B * keep + (hB - B * keep) * tint, lab)
      out[p] = lab[0]; out[p + 1] = lab[1]; out[p + 2] = lab[2]
    }
  }
  // 블러셔: 피부 색상과 목표 색상을 섞고(70%), 채도는 목표 쪽으로, 명도는 거의 유지
  // (색상을 통째로 바꾸고 채도를 .32 이상으로 끌어올리면 연한 핑크가 피부 위에서 연보라·마젠타 덩어리로 뜸)
  if (active('blush')) {
    const [th, ts, tv] = rgbToHsv(...hexToRgb(s.blush.hex)), k = s.blush.amount * 0.7, m = variants.blush[s.blush.shape], tip = (s.blush.tip ?? 0) * .7
    for (let i = 0, p = 0; i < n; i++, p += 4) {
      // 코끝 블러셔는 따로 세기 (쉐딩처럼 살짝)
      const a = Math.max(m[i] * k, face.blushNose[i] * tip)
      if (a < 0.002) continue
      const [sh, sat, v] = rgbToHsv(out[p], out[p + 1], out[p + 2])
      hsvToRgb(mixHue(sh, th, .7), sat + (Math.max(sat + .08, ts) - sat) * .85, v * (.92 + tv * .06), tmp)
      out[p] += (tmp[0] - out[p]) * a; out[p + 1] += (tmp[1] - out[p + 1]) * a; out[p + 2] += (tmp[2] - out[p + 2]) * a
    }
  }
  // 블러셔 광: 흰 광이 아닌 블러셔 색이 45% 섞인 광을 스크린으로. 블러셔가 칠해진 곳 × 광대 윗부분 × 원래 밝은 피부에만.
  const glow = Math.min(1, Math.max(0, s.blush.glow ?? 0))
  if (active('blush') && glow > 0) {
    const [r, g, b] = hexToRgb(s.blush.hex), m = variants.blush[s.blush.shape]
    const tint = [255 - (255 - r) * .45, 255 - (255 - g) * .45, 255 - (255 - b) * .45]
    const k = glow * .2 * Math.min(1, s.blush.amount * 2.5)
    for (let i = 0, p = 0; i < n; i++, p += 4) {
      const a = Math.min(1, m[i] * 1.4) * face.cheekGlow[i] * k
      if (a < 0.002) continue
      for (let c = 0; c < 3; c++) out[p + c] += a * (255 - out[p + c]) * tint[c] / 255
    }
  }
  // 아이섀도우: 저채도 음영. 피부 명암을 유지하며 살짝 어둡게 해 밝은 색이 페인트처럼 뜨지 않도록 한다.
  // 애교살 아래 주름: 살짝 어둡게 (애교살 자체 색은 아래 섀도 공통 처리에서)
  if (active('aegyo')) {
    const k = Math.min(1, s.aegyo.amount), ms = face.aegyoShadow[s.aegyo.shape]
    for (let i = 0, p = 0; i < n; i++, p += 4) {
      const d = ms[i] * k * .18
      if (d > .002) { out[p] *= 1 - d * .9; out[p + 1] *= 1 - d; out[p + 2] *= 1 - d }
    }
  }
  // 섀도 공통 (눈두덩 → 눈꼬리 포인트 → 애교살 → 아래 눈가 순으로 겹침)
  // 애교살은 밝히지 않고 섀도를 칠함 (흰빛으로 밝히면 떠 보임)
  const shadowMasks = { eyeshadow: variants.eyeshadow[s.eyeshadow.shape], shadowPoint: variants.shadowPoint[s.shadowPoint.shape], aegyo: variants.aegyo[s.aegyo.shape], underShadow: variants.underShadow[s.underShadow.shape] }
  for (const part of ['eyeshadow', 'shadowPoint', 'aegyo', 'underShadow'] as const) {
    if (!active(part)) continue
    const [th, ts, tv] = rgbToHsv(...hexToRgb(s[part].hex))
    // 높은 강도에서 너무 일찍 포화되지 않게 5단계 차이를 남긴다.
    // 애교살은 넓은 면이라 같은 강도면 눈 밑 그늘(다크서클)처럼 보여 75%만
    const k = (1-Math.pow(1-Math.min(1,s[part].amount),1.8)) * (part === 'aegyo' ? AEGYO_SHADOW : 1)
    const m = shadowMasks[part]
    // 목표색이 밝을수록(밝기 .6~.8) 물들이는 방식 비중을 높임, 브라운은 기존 음영 방식
    const tint = Math.min(1, Math.max(0, (tv - .6) / .2)), tint2 = [0, 0, 0]
    for (let i = 0, p = 0; i < n; i++, p += 4) {
      const a = m[i] * k
      if (a < 0.002) continue
      const [, sat, v] = rgbToHsv(out[p], out[p + 1], out[p + 2])
      if (tint > 0) {
        // 밝은 색(핑크·피치): 블러셔처럼 피부를 물들임 (색상을 통째로 바꾸고 어둡게 하면 보라 줄처럼 보임)
        const [sh, , ] = rgbToHsv(out[p], out[p + 1], out[p + 2])
        const hue = mixHue(sh, th, .75)
        hsvToRgb(hue, sat + (Math.max(.28, ts) - sat) * .8, v * (.9 + tv * .07), tint2)
      }
      hsvToRgb(th, Math.min(.38, sat * .3 + ts * .7), Math.max(.03, v * (.58 + tv * .25)), tmp)
      if (tint > 0) for (let c = 0; c < 3; c++) tmp[c] += (tint2[c] - tmp[c]) * tint
      out[p] += (tmp[0] - out[p]) * a; out[p + 1] += (tmp[1] - out[p + 1]) * a; out[p + 2] += (tmp[2] - out[p + 2]) * a
    }
  }
  // 눈두덩 펄: 눈두덩 가운데에 아주 옅은 윤기 + 작은 반짝임 점 (도치)
  const shimmer = Math.min(1, s.eyeshadow.shimmer ?? 0)
  if (active('eyeshadow') && shimmer > 0) {
    for (let i = 0, p = 0; i < n; i++, p += 4) {
      const m = face.lidShine[i] * shimmer
      if (m < .005) continue
      // 픽셀마다 고정된 난수로 7%만 반짝임 점
      const r = Math.sin(i * 12.9898) * 43758.5453, spark = r - Math.floor(r) > .93 ? 1 : 0
      const a = m * (.18 + .5 * spark)
      out[p] += (255 - out[p]) * a; out[p + 1] += (255 - out[p + 1]) * a * .97; out[p + 2] += (255 - out[p + 2]) * a * .92
    }
  }
  if (active('eyeliner')) {
    const color = hexToRgb(s.eyeliner.hex), mask = variants.eyeliner[s.eyeliner.shape]
    const lumaC = Math.max(1, color[0] * .299 + color[1] * .587 + color[2] * .114)
    for (let i = 0, p = 0; i < n; i++, p += 4) {
      // 완전 불투명이면 페인트처럼 납작 → 최대 .88로 피부결이 살짝 비치게
      // 강도 → 진하기를 부드럽게 (예전 min(.88, 강도×1.2)는 .73부터 최대에 걸려 그 위로는 슬라이더를 올려도 똑같았음)
      const alpha = mask[i] * .88 * (1 - (1 - Math.min(1, s.eyeliner.amount)) ** 2)
      if (alpha < .002) continue
      // 어둡게만: 원래 더 어두운 곳(실제 속눈썹 라인)은 라인 색을 그 밝기로 낮춤
      // (연브라운을 그대로 덮으면 검은 속눈썹 라인이 회갈색 띠로 밝아짐)
      const k = Math.min(1, (out[p] * .299 + out[p + 1] * .587 + out[p + 2] * .114) / lumaC)
      for (let c = 0; c < 3; c++) out[p + c] += (color[c] * k - out[p + c]) * alpha
    }
  }
  // 립: 색상 교체, 채도는 목표 쪽으로, 명도는 원본 명암 유지 + 목표 밝기로 이동
  if (active('lip')) {
    const glossyLip = s.lip.shape === 'glossy'
    const [th, ts, tv] = rgbToHsv(...hexToRgb(s.lip.hex)), k = s.lip.amount * (glossyLip ? 0.72 : 1), m = s.lip.soft ? variants.lip.blur : variants.lip[s.lip.shape], shift = (tv - face.lipMeanV) * 0.75
    for (let i = 0, p = 0; i < n; i++, p += 4) {
      const a = m[i] * k
      if (a < 0.002) continue
      const [, sat, v] = rgbToHsv(out[p], out[p + 1], out[p + 2])
      // 그라데이션은 안쪽(마스크 진한 곳)을 한 톤 더 깊게
      const deepen = s.lip.shape === 'gradient' ? m[i] * .14 : 0
      hsvToRgb(th, sat + (ts - sat) * 0.9, Math.min(1, Math.max(0.03, v + shift - deepen - face.lipSpecular[i] * (glossyLip ? .35 : .95))), tmp)
      out[p] += (tmp[0] - out[p]) * a; out[p + 1] += (tmp[1] - out[p + 1]) * a; out[p + 2] += (tmp[2] - out[p + 2]) * a
    }
    // 글로시 광: 입술 전체 물광 없이, 원래 입술의 밝은 굴곡을 따라 부분부분 작은 반사광만
    // (정해진 타원을 고르게 밝히면 하얀 줄처럼 보임)
    // 촉촉립이 아니어도 gloss 값만큼 같은 광을 약하게 (남성: 그라데이션 립에 광 정도만 다르게)
    const gloss = glossyLip ? 1 : Math.min(1, s.lip.gloss ?? 0)
    if (gloss > 0) {
      const amt = Math.min(1, s.lip.amount) * gloss
      for (let i = 0, p = 0; i < n; i++, p += 4) {
        const existingShine = Math.min(1,face.lipSpecular[i]/.10)
        // 원본에 있는 젖은 광택 위에 하이라이트를 중복해서 쌓지 않는다 (existingShine)
        const rel = face.lipRel[i], ridge = rel * rel * (3 - 2 * rel)
        // 입술 결을 조금 반영해 작은 점들이 부분부분 끊겨 맺히게 (세게 하면 가로 결이 줄무늬로 강조됨)
        // 입술 결(밝은 굴곡)을 더 따라가게 해 고르게 덮인 흰 막이 아니라 결 위에 맺힌 윤기처럼
        const a = Math.min(1, face.lipGloss[i] * amt * LIP_GLOSS * (.35 + .65 * ridge) * (1 - face.lipShine * .5) * (1 - existingShine))
        out[p] += (255 - out[p]) * a
        out[p + 1] += (255 - out[p + 1]) * a * 0.96
        out[p + 2] += (255 - out[p + 2]) * a * 0.94
      }
    }
  }
}
