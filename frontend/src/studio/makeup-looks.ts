import { DEFAULT_MAKEUP, labToHex, type MakeupPart, type MakeupSettings, type MakeupShapes } from './makeup'

export type Undertone = 'warm' | 'neutral' | 'cool'
export type Brightness = 'light' | 'medium' | 'deep'
export type FaceShape = 'oval' | 'round' | 'square' | 'long' | 'heart' | 'diamond'
export type PaletteId = 'light' | 'signature' | 'accent' | 'lip' | 'eye'
export type MakeupSex = 'female' | 'male'
export type MakeupOccasion = 'daily' | 'formal' | 'outdoor' | 'party'
export type LookId = string
// 톤·밝기는 피부톤 분석(undertone·brightness_level)과 같은 축, 분석 결과가 없으면 사용자가 고름
// 쿠션: 피부톤 분석의 palette.cushion (예: '22~23호 범위 · 핑크조'), 없으면 톤·밝기로 정함
export type CushionBase = 'pink' | 'neutral' | 'yellow'
export type Cushion = { shade: number; base: CushionBase }
// faceShape 'auto': 사진 분석(얼굴 맞춤)으로 정함, 룩 추천에는 정해진 얼굴형만 넘김
// lipPale: 사진 속 입술이 창백한 정도 0~1 (lipPaleness, 없으면 0)
export type MakeupProfile = { tone: Undertone; brightness: Brightness; faceShape: FaceShape | 'auto'; sex: MakeupSex; cushion?: Cushion; lipPale?: number }
// lashes: 위 속눈썹 에셋 id (static/makeup/lashes/catalog.json), 'none'이면 없음
// brow: 룩 기본 눈썹 (없으면 눈썹 안 바꿈)
export type MakeupLook = { id: LookId; name: string; mood: string; description: string; occasion: MakeupOccasion; lashes: string; brow?: string; settings: MakeupSettings }
type ColorSet = { name: string; eyeshadow: string; lip: string; blush: string }
export const TONES: { id: Undertone; label: string; description: string }[] = [
  { id: 'warm', label: '웜', description: '피치·살구 코랄부터 브릭까지, 섀도는 카멜 브라운' },
  { id: 'neutral', label: '뉴트럴', description: '누드 베이지·MLBB·말린 장미, 섀도는 토프 브라운' },
  { id: 'cool', label: '쿨', description: '핑크 베이지·쿨 로즈부터 플럼 베리까지, 섀도는 로즈 브라운' },
]
export const BRIGHTNESS: { id: Brightness; label: string }[] = [
  { id: 'light', label: '밝은 피부' }, { id: 'medium', label: '중간 피부' }, { id: 'deep', label: '어두운 피부' },
]
export const FACE_SHAPES: { id: FaceShape; label: string }[] = [
  { id: 'oval', label: '계란형' }, { id: 'round', label: '둥근형' }, { id: 'square', label: '사각형' },
  { id: 'long', label: '긴형' }, { id: 'heart', label: '하트형' }, { id: 'diamond', label: '다이아몬드형' },
]
// 톤별 5칸: light(옅은색)·signature(대표색)·accent(포인트)·lip(진한 립)·eye(눈 음영 중심)
// 채도는 데일리로 바를 수 있는 수준까지만, 진한 색은 lip 칸에만
// 섀도: 옅은색·포인트 칸은 핑크·피치, 나머지는 브라운 (회보라는 눈에 칠하면 멍든 것처럼 보여 뺌)
// HEX는 가상 메이크업용으로 구성한 색이며 진단용 표준 색상이 아님
export const TONE_PALETTES: Record<Undertone, Record<PaletteId, ColorSet>> = {
  warm: {
    light: { name: '피치 누드', eyeshadow: '#d49a84', lip: '#e0907a', blush: '#f2b096' },
    signature: { name: '살구 코랄', eyeshadow: '#a5856c', lip: '#d9735a', blush: '#eda080' },
    accent: { name: '코랄 핑크', eyeshadow: '#cf8c80', lip: '#e06a6a', blush: '#ef9a8e' },
    lip: { name: '브릭 레드', eyeshadow: '#957763', lip: '#b8483a', blush: '#d98a72' },
    eye: { name: '카멜 브라운', eyeshadow: '#86684f', lip: '#c26f55', blush: '#d9976f' },
  },
  neutral: {
    light: { name: '누드 베이지', eyeshadow: '#c99a8f', lip: '#d49488', blush: '#e8b0a2' },
    signature: { name: 'MLBB 로즈', eyeshadow: '#9c8476', lip: '#c4746e', blush: '#e09a92' },
    accent: { name: '말린 장미', eyeshadow: '#bd8786', lip: '#b86a6c', blush: '#d6948f' },
    lip: { name: '로즈 레드', eyeshadow: '#8c756b', lip: '#a8474f', blush: '#cc8584' },
    eye: { name: '토프 브라운', eyeshadow: '#7a665b', lip: '#b67a6e', blush: '#d29a8c' },
  },
  cool: {
    light: { name: '핑크 베이지', eyeshadow: '#d09aa6', lip: '#d8939a', blush: '#ecb2bc' },
    signature: { name: '쿨 로즈', eyeshadow: '#9a8484', lip: '#c46a80', blush: '#e096a8' },
    accent: { name: '베리 로즈', eyeshadow: '#c08494', lip: '#b4586e', blush: '#d48a9c' },
    lip: { name: '플럼 베리', eyeshadow: '#86707a', lip: '#93405c', blush: '#c47c90' },
    eye: { name: '로즈 브라운', eyeshadow: '#76615f', lip: '#ad6f74', blush: '#cf98a2' },
  },
}
// 쿠션 호수별 밝기(L)·베이스별 색(a·b) (가상 메이크업용 근사값, 실제 제품 색이 아님)
const SHADE_L: [number, number][] = [[13, 79], [17, 76], [19, 74], [21, 71], [23, 67], [25, 63]]
const BASE_AB: Record<CushionBase, [number, number]> = { pink: [11, 13], neutral: [9, 15], yellow: [7, 18] }
export function cushionHex({ shade, base }: Cushion) {
  const i = SHADE_L.findIndex(([s]) => s >= shade)
  const [s0, l0] = SHADE_L[Math.max(0, i - 1)], [s1, l1] = SHADE_L[i < 0 ? SHADE_L.length - 1 : i]
  const L = s1 === s0 ? l1 : l0 + (l1 - l0) * (shade - s0) / (s1 - s0)
  return labToHex(L, BASE_AB[base][0], BASE_AB[base][1])
}
const TONE_CUSHION: Record<Undertone, CushionBase> = { warm: 'yellow', neutral: 'neutral', cool: 'pink' }
// 밝기 단계별 대표 호수 (백엔드 범위 17~21 / 22~23 / 24호 이상에서 cushionFromAnalysis가 꺼내는 값과 같음)
const BRIGHT_SHADE: Record<Brightness, number> = { light: 19, medium: 22.5, deep: 25 }
// 애교살 섀도: 피치 베이지 / 로지 베이지 / 모브 핑크 (밝은 색이라 피부를 물들이는 방식으로 칠해짐)
const AEGYO_COLOR: Record<Undertone, string> = { warm: '#dca58f', neutral: '#d4a19b', cool: '#cc9ca6' }
// 립에 섞는 베이지 (톤별: 웜 카멜 베이지 / 뉴트럴 로지 베이지 / 쿨 모브 베이지)
// 립 탁기: 회색빛 로즈브라운
const LIP_MUTED = '#8f716c'
// 창백한 입술 맞춤: 가장 창백할 때 베이지를 줄이는 비율 · 립 강도를 올리는 비율 (최대 1.25배, 창백도 .67 이상이면 최대)
// · 립 채도를 올리는 비율 (최대 +12%, "너무 강하다"로 .25→.12, 색 계열은 그대로 발색만, 2026-11-15 "입술색 너무 없는 사람")
const LIP_PALE_BEIGE = .75, LIP_PALE_BOOST = .25, LIP_PALE_SAT = .12
// 창백한 입술에 톤별 색(lipTint)을 섞는 최대 비율 (창백도 1일 때)
const LIP_PALE_TINT = .5
// 여성 눈 화장(섀도 3칸·아이라인) 강도 배율 (2026-11-15 "조금씩 더 강하게", 애교살·속눈썹은 제외)
const FEMALE_EYE_BOOST = 1.15
const LIP_BEIGE: Record<Undertone, string> = { warm: '#c9977f', neutral: '#c39589', cool: '#bd9290' }
// HSL 채도만 배율 (색상·명도 그대로)
function saturateHex(hex: string, k: number) {
  const n = parseInt(hex.slice(1), 16), r = (n >> 16 & 255) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min
  if (!d) return hex
  const S = Math.min(1, d / (1 - Math.abs(2 * l - 1)) * k)
  const h = max === r ? ((g - b) / d + 6) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4
  const c = (1 - Math.abs(2 * l - 1)) * S, x = c * (1 - Math.abs(h % 2 - 1)), m = l - c / 2
  const [R, G, B] = h < 1 ? [c, x, 0] : h < 2 ? [x, c, 0] : h < 3 ? [0, c, x] : h < 4 ? [0, x, c] : h < 5 ? [x, 0, c] : [c, 0, x]
  return '#' + [R, G, B].map(v => Math.round((v + m) * 255).toString(16).padStart(2, '0')).join('')
}
function mixHex(a: string, b: string, t: number) {
  const x = parseInt(a.slice(1), 16), y = parseInt(b.slice(1), 16)
  return '#' + [16, 8, 0].map(sh => Math.round((x >> sh & 255) * (1 - t) + (y >> sh & 255) * t).toString(16).padStart(2, '0')).join('')
}
// 톤별 쉐딩·아이라인(진한/기본)·하이라이터 색 (진한 라인은 흑갈색, 회보라는 페인트처럼 보임)
const TONE_BASE: Record<Undertone, { shade: string; liner: [string, string]; highlight: string }> = {
  warm: { shade: '#a08470', liner: ['#3f2c22', '#80624f'], highlight: '#fff0da' },
  neutral: { shade: '#9a8274', liner: ['#382a24', '#7a6558'], highlight: '#fbf0e6' },
  cool: { shade: '#91807f', liner: ['#332a2b', '#74666a'], highlight: '#f9edef' },
}
// 밝기별 색 깊이: HSL 명도·채도 이동 (밝은 피부는 맑고 옅게, 어두운 피부는 깊고 진하게 해야 떠 보이지 않음)
// 2026-11-15 밝은 피부 옅게 보정 완화 (l .05→.02, s -.04→0): 사용자 대부분이 밝은 피부로 잡혀 메이크업이 티가 안 났음
const BRIGHTNESS_SHIFT: Record<Brightness, { l: number; s: number }> = { light: { l: .02, s: 0 }, medium: { l: 0, s: 0 }, deep: { l: -.08, s: .04 } }
// 레퍼런스 색을 톤 쪽으로: HSL 색상을 톤 중심(웜 코랄·뉴트럴 로즈 베이지·쿨 로즈) 쪽으로 40% 이동
const TONE_HUE: Record<Undertone, number> = { warm: 18, neutral: 4, cool: 345 }
function toneHex(hex: string, tone: Undertone, strength = .4) {
  const n = parseInt(hex.slice(1), 16), r = (n >> 16 & 255) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min
  if (d < .04) return hex  // 무채색에 가까우면 그대로
  const s = d / (1 - Math.abs(2 * l - 1))
  let h = (max === r ? ((g - b) / d + 6) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4) * 60
  let diff = TONE_HUE[tone] - h
  if (diff > 180) diff -= 360
  if (diff < -180) diff += 360
  h = (h + diff * strength + 360) % 360
  const c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = l - c / 2, k = Math.floor(h / 60)
  const [R, G, B] = k === 0 ? [c, x, 0] : k === 1 ? [x, c, 0] : k === 2 ? [0, c, x] : k === 3 ? [0, x, c] : k === 4 ? [x, 0, c] : [c, 0, x]
  return '#' + [R, G, B].map(v => Math.round((v + m) * 255).toString(16).padStart(2, '0')).join('')
}
// 웜톤: 가볍게 — 눈가는 라이트 베이지·구운 베이지, 볼·입술은 코랄 (진하고 붉은 웜 브라운이 무거워 보임)
// 부위별 목표 색상(도)·옮기는 비율·밝기 올림·채도 배율
const WARM_STYLE: Record<'eyeshadow' | 'blush' | 'lip', { hue: number; strength: number; dl: number; sat: number }> = {
  eyeshadow: { hue: 26, strength: .65, dl: .07, sat: .8 },
  blush: { hue: 16, strength: .65, dl: .04, sat: .95 },
  lip: { hue: 14, strength: .55, dl: .06, sat: .92 },
}
function warmHex(hex: string, key: 'eyeshadow' | 'blush' | 'lip') {
  const { hue, strength, dl, sat } = WARM_STYLE[key]
  const n = parseInt(hex.slice(1), 16), r = (n >> 16 & 255) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min
  const s0 = d ? d / (1 - Math.abs(2 * l - 1)) : 0
  let h = !d ? hue : (max === r ? ((g - b) / d + 6) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4) * 60
  let diff = hue - h
  if (diff > 180) diff -= 360
  if (diff < -180) diff += 360
  h = ((h + diff * strength) % 360 + 360) % 360 / 60
  const L = Math.min(.92, l + dl), S = Math.min(1, s0 * sat)
  const c = (1 - Math.abs(2 * L - 1)) * S, x = c * (1 - Math.abs(h % 2 - 1)), m = L - c / 2
  const [R, G, B] = h < 1 ? [c, x, 0] : h < 2 ? [x, c, 0] : h < 3 ? [0, c, x] : h < 4 ? [0, x, c] : h < 5 ? [x, 0, c] : [c, 0, x]
  return '#' + [R, G, B].map(v => Math.round((v + m) * 255).toString(16).padStart(2, '0')).join('')
}
function shiftHex(hex: string, brightness: Brightness) {
  const { l: dl, s: ds } = BRIGHTNESS_SHIFT[brightness]
  if (!dl && !ds) return hex
  const n = parseInt(hex.slice(1), 16), r = (n >> 16 & 255) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min
  const s = d ? d / (1 - Math.abs(2 * l - 1)) : 0
  const h = !d ? 0 : max === r ? ((g - b) / d + 6) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4
  const L = Math.min(.95, Math.max(.05, l + dl)), S = Math.min(1, Math.max(0, s + ds))
  const c = (1 - Math.abs(2 * L - 1)) * S, x = c * (1 - Math.abs(h % 2 - 1)), m = L - c / 2
  const [R, G, B] = h < 1 ? [c, x, 0] : h < 2 ? [x, c, 0] : h < 3 ? [0, c, x] : h < 4 ? [0, x, c] : h < 5 ? [x, 0, c] : [c, 0, x]
  return '#' + [R, G, B].map(v => Math.round((v + m) * 255).toString(16).padStart(2, '0')).join('')
}
// 룩에 턱 쉐딩·하이라이터 모양이 없을 때 얼굴형 기본값
const PLACEMENT: Record<FaceShape, { shading: MakeupShapes['shading']; highlight: MakeupShapes['highlight'] }> = {
  oval: { shading: 'natural', highlight: 'standard' },
  round: { shading: 'vline', highlight: 'center' },
  square: { shading: 'natural', highlight: 'cheek' },
  long: { shading: 'chin', highlight: 'cheek' },
  heart: { shading: 'natural', highlight: 'cheek' },
  diamond: { shading: 'chin', highlight: 'center' },
}
export const MAKEUP_SEXES: { id: MakeupSex; label: string; description: string }[] = [
  { id: 'female', label: '여성', description: '피부 톤 발색 중심의 상황별 메이크업' },
  { id: 'male', label: '남성', description: '눈썹·윤곽·혈색 위주로 티 안 나게 다듬는 그루밍 메이크업' },
]
// 룩 = 모양·강도만 (색은 피부 톤 팔레트 칸, 위치는 얼굴형 배치에서)
// 여성 12개는 레퍼런스 사진(makeup-ref) 10장 분류, 강도는 테스트 사진에 입혀 레퍼런스와 비교해 맞춤
// (블러셔 ×2·섀도 ×1.8·라인·하이라이트 ×1.3 올림, 3배부터 블러셔가 도장처럼 보임)
export const MAKEUP_OCCASIONS: { id: MakeupOccasion; label: string; description: string }[] = [
  { id: 'daily', label: '데일리', description: '가볍게 매일 하는 메이크업' },
  { id: 'formal', label: '격식', description: '출근·면접·하객처럼 단정해야 하는 자리' },
  { id: 'outdoor', label: '야외', description: '자연광에서 생기 있게 보이는 메이크업' },
  { id: 'party', label: '파티', description: '사진·조명에서 또렷하게 보이는 포인트 메이크업' },
]
export const MALE_OCCASIONS: { id: MakeupOccasion; label: string; description: string }[] = [
  { id: 'daily', label: '데일리', description: '피부 톤과 눈썹만 정리한 듯 티 안 나게' },
  { id: 'formal', label: '격식', description: '매트하고 단정하게, 신뢰감 있는 인상' },
  { id: 'outdoor', label: '야외', description: '자연광에서 건강해 보이는 최소한의 표현' },
  { id: 'party', label: '파티', description: '조명·카메라에 묻히지 않게 윤곽과 눈매를 또렷하게' },
]
export function occasionsFor(sex: MakeupSex) {
  return sex === 'male' ? MALE_OCCASIONS : MAKEUP_OCCASIONS
}

// 부위별 [색, 모양, 강도], 강도 0이면 끔
// 색: 팔레트 칸(톤별 팔레트) 또는 레퍼런스에서 뽑은 '#hex' (톤 쪽으로 색상만 살짝 옮겨 씀)
type ColorRef = PaletteId | `#${string}`
type Recipe = {
  name: string; description: string; lashes?: string
  eye: [ColorRef, MakeupShapes['eyeshadow'], number]
  point?: [ColorRef, MakeupShapes['shadowPoint'], number]
  under?: [ColorRef, MakeupShapes['underShadow'], number]
  aegyo?: number  // 애교살 강도
  aegyoShape?: MakeupShapes['aegyo']
  lipBeige?: number  // 립 색에 베이지를 섞는 비율 (0~1, 없으면 안 섞음)
  lipTint?: Partial<Record<Undertone, `#${string}`>>  // 창백한 입술일 때만 섞는 톤별 색 (베이지 립이 생 베이지로 보이지 않게)
  shadingShape?: MakeupShapes['shading']  // 턱 쉐딩 모양 (없으면 얼굴형 배치)
  noseShape?: MakeupShapes['noseShading']  // 코 쉐딩 모양 (없으면 부드러운 콧대)
  lipMuted?: number  // 립 색에 탁한 로즈브라운을 섞는 비율 (탁기)
  lipSoft?: boolean  // 립 경계 흐리게
  lipGloss?: number  // 립 모양과 따로 넣는 은은한 광 (0~1)
  brow?: string  // 룩 기본 눈썹 에셋 id (남성: 빈 곳 채우기)
  cleft?: number  // 엉덩이턱 음영 (남성)
  noseCleft?: number  // 엉덩이코 (코끝 가운데 음영 + 양쪽 하이라이트)
  lipBy?: Partial<Record<Undertone, `#${string}`>>  // 톤별 립 색 직접 지정 (톤 이동 없이 밝기만 조정, 립은 채도를 거의 그대로 따라가 채도 높으면 쨍한 보라·주황이 됨)
  blushBy?: Partial<Record<Undertone, `#${string}`>>  // 톤별 블러셔 색 직접 지정
  blushTip?: number  // 코끝 블러셔 (쉐딩처럼 살짝)
  shimmer?: number  // 눈두덩 펄
  highlightHex?: `#${string}`  // 하이라이터 색 (골드 펄 등)
  skin?: number  // 피부 보정 강도 (없으면 여성 .55·남성 .7)
  liner: [MakeupShapes['eyeliner'], number]
  blush: [ColorRef, MakeupShapes['blush'], number, number]  // 마지막은 광
  lip: [ColorRef, MakeupShapes['lip'], number]
  shading: number; nose: number
  highlight: [MakeupShapes['highlight'] | null, number]  // null이면 얼굴형 배치
}
// 여성 룩: makeup-ref 레퍼런스에서 부위별 색·세기를 뽑아 채움 (번호는 레퍼런스 파일 번호)
// 섀도는 눈두덩(eye)·눈꼬리 포인트(point)·아래 눈가(under) 3색, 색은 레퍼런스 피부 대비 차이를 1.6배로 늘려 화장품 색으로 되돌린 값
// 단정 라인(8)·코끝 치크(9)는 레퍼런스가 설명 그림이라 팔레트 칸 사용
// 립은 입술에서 반사광·그늘을 빼고 채도 상위 35% 픽셀로 다시 뽑음 (밝은 쪽 평균은 필터·광에 묽어져 다 비슷한 로즈였음)
const FEMALE: Record<MakeupOccasion, Recipe[]> = {
  daily: [
    { name: '내추럴', lashes: 'none', description: '거의 맨얼굴처럼, 눈가에 옅은 웜 브라운과 넓고 옅은 볼, 물든 듯한 립.',  // 10
      eye: ['#926e65', 'basic', .3], point: ['#6e514c', 'wing', .25], under: ['#a26760', 'outer', .29], liner: ['basic', .6], blush: ['#eeb0a7', 'wide', .52, .5], lip: ['#96353e', 'gradient', .5], lipBy: { warm: '#b5483f', cool: '#a83a5a' }, lipBeige: 0.4, shading: .1, nose: .07, highlight: ['standard', .39] },
    { name: '핑크', lashes: '02_lash_overlay', description: '눈두덩은 베이지 음영으로, 아래 눈가와 애교살로 맑게. 볼은 넓게, 입술은 촉촉하게.',  // 5
      eye: ['#a68b7d', 'basic', .6], point: ['#8c6e62', 'wing', .55], under: ['#ae7078', 'outer', .35], aegyo: .6, liner: ['basic', .6], blush: ['#e2acae', 'wide', .55, .3], lip: ['#a14c5d', 'glossy', .6], lipBy: { cool: '#98506a' }, blushTip: .3, shading: .12, nose: .08, highlight: ['standard', .33] },
    { name: '피치', lashes: '05_lash_overlay', description: '소프트 브라운 눈가에 볼 중앙 피치, 입술은 안쪽부터 물들여요.',  // 12
      eye: ['#735546', 'basic', .45], point: ['#5b453c', 'wing', .35], under: ['#93675a', 'outer', .35], liner: ['basic', .52], blush: ['#cd988c', 'round', .68, .2], lip: ['#a3464d', 'gradient', .6], lipBy: { warm: '#b8573f' }, blushBy: { warm: '#e3a07f' }, lipBeige: 0.3, shading: .14, nose: .1, highlight: ['cheekNose', .45] },
  ],
  formal: [
    // 우롱차 메이크업 레퍼런스: 전체 베이지 톤, 립·블러셔는 톤별 지정 (웜에서 코랄로 안 바뀌게)
    { name: '베이지', lashes: '05_lash_overlay', description: '눈가는 밀크티 베이지, 아래 눈가는 옅은 브라운으로 순하게. 볼은 거의 안 보이게, 입술은 누드 베이지 윤기.',
      eye: ['#b39582', 'basic', .45], point: ['#8a6c5c', 'wing', .3], under: ['#8f6c5c', 'outer', .4], liner: ['down', .45], blush: ['#e2b8a4', 'wide', .3, .4], blushBy: { warm: '#e6b89c', cool: '#e0b4aa' }, lip: ['#c48d82', 'glossy', .55], lipBy: { warm: '#c58f78', neutral: '#c48d82', cool: '#c08a88' }, lipBeige: .35, lipTint: { warm: '#d9826a', neutral: '#cf7f7e', cool: '#cc7d92' }, shading: .1, nose: .08, highlight: ['standard', .4] },
    { name: '뮤트', lashes: '05_lash_overlay', description: '광 없이 매트하게, 토프 눈가와 모브 블러립으로 정돈된 인상.',  // 3
      eye: ['#746158', 'basic', .4], point: ['#67554e', 'wing', .2], under: ['#7c6062', 'outer', .3], liner: ['basic', .65], blush: ['#eecab6', 'slim', .3, 0], lip: ['#7e3440', 'blur', .7], lipBy: { warm: '#b06552' }, blushBy: { warm: '#ecb291' }, shading: .3, nose: .25, highlight: [null, .07] },
    { name: '도치', lashes: '05_lash_overlay', description: '아래 눈가에 무게를 두고 꼬리를 내린 라인, 애교살로 순하고 어려 보이게.',  // 8 오른쪽(도치 메이크업)
      eye: ['#a58378', 'basic', .4], point: ['#8a6560', 'wing', .3], under: ['#a26770', 'wide', .38], aegyo: .5, aegyoShape: 'long', liner: ['down', .6], blush: ['#e2acae', 'undereye', .4, .3], lip: ['#b05a68', 'gradient', .6], lipBeige: 0.25, shimmer: .25, shading: .15, nose: .1, highlight: ['center', .2] },
  ],
  outdoor: [
    { name: '혈색', lashes: '05_lash_overlay', description: '코끝과 눈 아래에 혈색을 더하고 꼬리를 내려 순하게.',  // 9
      eye: ['light', 'basic', .36], aegyo: .4, liner: ['down', .59], blush: ['signature', 'teary', .7, .3], lip: ['signature', 'gradient', .55], shading: .1, nose: .07, highlight: ['center', .45] },
    { name: '숙취', lashes: '02_lash_overlay', description: '눈 밑에서 콧등까지 발그레하게 잇고, 아래 눈가도 물들여요. 입술은 촉촉하게.',  // 4
      eye: ['#8f6b63', 'basic', .35], under: ['#815a5b', 'outer', .5], aegyo: .5, liner: ['basic', .7], blush: ['#f4a0ad', 'hangover', .8, .6], lip: ['#c8606e', 'glossy', .55], lipMuted: .25, shading: .12, nose: .08, highlight: ['standard', .45] },
    { name: '브론즈', lashes: '02_lash_overlay', description: '피부에 광을 주고 눈가를 브론즈 브라운으로 번지게, 광대는 브론즈빛으로.',  // 11
      eye: ['#6a4c45', 'basic', .48], point: ['#67463e', 'smoky', .35], under: ['#77534c', 'outer', .35], liner: ['down', .6], blush: ['#b27b6e', 'diagonal', .5, .6], lip: ['#7e2f3c', 'blur', .75], lipBy: { warm: '#8a4232' }, shading: .3, nose: .2, highlight: ['cheekChin', .6], highlightHex: '#f6d9a2' },
  ],
  party: [
    { name: '로즈', lashes: '03_lash_overlay', description: '눈두덩부터 아래 눈가까지 로즈 브라운으로 번지고, 경계를 푼 블러립으로 차분하게.',  // 2
      eye: ['#855b54', 'basic', .75], point: ['#77544d', 'wing', .85], under: ['#78474b', 'full', .55], liner: ['longDown', .52], blush: ['#dfb3a9', 'ennui', .35, 0], lip: ['#7a2e3a', 'blur', .85], lipBy: { cool: '#86434f' }, shading: .22, nose: .15, highlight: [null, .1] },
    { name: '아이돌', lashes: '06_lash_overlay', description: '볼 중앙을 진하게 물들이고 눈꼬리·아래 눈가에 음영, 안쪽부터 물든 립.',  // 7
      eye: ['#7e5954', 'basic', .6], point: ['#835d57', 'wing', .6], under: ['#754b4d', 'outer', .55], aegyo: .6, liner: ['down', .78], blush: ['#e0707f', 'round', .75, 0], lip: ['#d23c55', 'gradient', .8], shading: .3, nose: .2, highlight: ['standard', .65] },
    { name: '시크', lashes: '03_lash_overlay', description: '눈꼬리 뒤까지 토프 음영을 빼고 진한 윙 라인, 창백한 매트 피부에 모브 블러립.',  // 3
      eye: ['#746158', 'basic', .6], point: ['#67554e', 'long', .65], under: ['#7c6062', 'outer', .35], liner: ['longWing', .78], blush: ['#eecab6', 'diagonal', .3, 0], lip: ['#6e2a36', 'blur', .85], lipBy: { warm: '#8a4335', cool: '#6f3a4c' }, shading: .4, nose: .3, highlight: [null, .13] },
    { name: '글리터', lashes: '03_lash_overlay', description: '맑은 눈가에 아래 눈가를 핑크로 넓게, 입술은 반짝이게.',  // 6
      eye: ['#baa49c', 'basic', .4], under: ['#b18a8e', 'full', .2], aegyo: .7, liner: ['basic', .45], blush: ['#f29aa6', 'undereye', .8, .7], lip: ['#e85a70', 'glossy', .8], lipSoft: true, shading: .2, nose: .14, highlight: ['center', .72] },
  ],
}
// 남성 그루밍: 색보다 강도 위주, 블러셔·하이라이트·아이섀도는 아주 옅게 또는 끔
// 남성: 아이라인·속눈썹 없음, 차이는 쉐딩(턱 모양·코 모양·세기)과 눈썹(룩마다 기본 눈썹, 빈 곳 채우기)으로
// 립: 모두 그라데이션, 입술에 붉은기를 넣은 로즈·레드 계열(레퍼런스 backend/ref 1~5), 광(lipGloss)만 0~.45로 다르게
// 블러셔: 전부 은은하게(.08~.22), 하이라이터는 펄 없는 매트 베이지로 콧대·턱끝만, 눈두덩은 아주 옅은 브라운
const MALE: Record<MakeupOccasion, Recipe[]> = {
  daily: [
    { name: '내추럴', description: '턱선만 옅게 정리하고 입술은 립밤처럼 은은한 MLBB로.',
      eye: ['eye', 'basic', .12], liner: ['basic', 0], blush: ['#e3a39a', 'wide', 0.1, 0], lip: ['#c27a74', 'gradient', .4], lipBeige: .3, lipGloss: 0.35, shading: 0.14, nose: 0.24, highlight: ['tzone', .12], highlightHex: '#f2e3d6', brow: 'M14_airy_natural' },
    { name: '클린', description: '콧대 옆면의 얇은 음영과 매트 하이라이트, 입술은 누드 코랄 베이지로 깔끔하게.',
      eye: ['eye', 'basic', .14], liner: ['basic', 0], blush: ['#e3a39a', 'wide', 0.1, 0], lip: ['#bf7666', 'gradient', .45], lipBeige: .35, lipGloss: 0.1, noseCleft: 0.1, noseShape: 'slim',  shading: 0.24, nose: 0.36, highlight: ['tzone', .19], highlightHex: '#f2e3d6', brow: 'M11_soft_straight' },
    { name: '생기', description: '볼에 옅은 혈색, 입술은 코랄 레드 틴트로 살짝 윤기 있게.',
      eye: ['eye', 'basic', .12], liner: ['basic', 0], blush: ['#e8a08c', 'wide', .2, .1], lip: ['#d2574d', 'gradient', .6], lipGloss: 0.45, shading: 0.17, nose: 0.24, highlight: ['tzone', .12], highlightHex: '#f2e3d6', brow: 'M14_airy_natural' },
  ],
  formal: [
    { name: '매트', description: '광 없이 매트하게, 짙은 일자 눈썹과 누드 로즈 매트 립으로 단정하게.',
      eye: ['eye', 'basic', .15], liner: ['basic', 0], blush: ['#e3a39a', 'wide', 0.08, 0], lip: ['#a8646a', 'blur', .5], lipMuted: .2, lipGloss: 0, noseCleft: 0.16, noseShape: 'slim', shadingShape: 'sculpt', cleft: 0.16, shading: 0.3, nose: 0.38, highlight: ['tzone', .12], highlightHex: '#f2e3d6', brow: 'M12_bold_straight' },
    { name: '단정', description: '턱끝과 코끝을 정돈하고 긴 일자 눈썹, 베이지 핑크 립으로 차분하게.',
      eye: ['eye', 'basic', .16], liner: ['basic', 0], blush: ['#e3a39a', 'wide', 0.1, 0], lip: ['#b97a70', 'gradient', .5], lipBeige: .25, lipGloss: 0.1, noseCleft: 0.1, noseShape: 'tip', shadingShape: 'chin', cleft: 0.15, shading: 0.3, nose: 0.34, highlight: ['tzone', .12], highlightHex: '#f2e3d6', brow: 'M16_long_straight' },
  ],
  outdoor: [
    { name: '톤업', description: '자연광에서는 최소한으로, 입술은 거의 무색 립밤 윤기만.',
      eye: ['eye', 'basic', .12], liner: ['basic', 0], blush: ['#efb0a8', 'wide', .15, .2], lip: ['#c98a82', 'gradient', .3], lipBeige: .2, lipGloss: 0.5, shading: 0.1, nose: 0.16, highlight: ['tzone', .12], highlightHex: '#f2e3d6', brow: 'M14_airy_natural' },
    { name: '헬시', description: '볼에 붉은 혈색, 입술은 체리 레드로 건강해 보이게.',
      eye: ['eye', 'basic', .12], liner: ['basic', 0], blush: ['#e39a8f', 'wide', .22, .1], lip: ['#c43744', 'gradient', .65], lipGloss: 0.3, noseShape: 'tip', shading: 0.17, nose: 0.26, highlight: ['tzone', .12], highlightHex: '#f2e3d6', brow: 'M15_full_soft_arch' },
    { name: '선번', description: '햇볕에 살짝 탄 듯 광대에서 콧등을 가로질러 잇고, 입술은 오렌지 코랄로 윤기 있게.',
      eye: ['eye', 'basic', .14], liner: ['basic', 0], blush: ['#e48a78', 'sunburn', .5, .2], lip: ['#cf6447', 'gradient', .55], lipGloss: 0.4, noseShape: 'tip', shading: 0.17, nose: 0.26, highlight: ['tzone', .12], highlightHex: '#f2e3d6', brow: 'M11_soft_straight' },
  ],
  party: [
    { name: '선명', description: '맑은 피부에 쿨 로즈 립, 턱선·콧대는 또렷하게.',
      eye: ['eye', 'basic', .18], liner: ['basic', 0], blush: ['#e3a39a', 'wide', 0.12, 0], lip: ['#bd4862', 'gradient', .62], lipGloss: 0.2, noseCleft: 0.24, noseShape: 'sculpted', shadingShape: 'vline',  cleft: 0.24, shading: 0.42, nose: 0.46, highlight: ['tzone', .32], highlightHex: '#f2e3d6', brow: 'M12_bold_straight' },
    { name: '샤프', description: '코끝·턱끝의 작은 홈과 광대 골격을 또렷하게, 브릭 매트 립. 넓은 광대·사각턱은 강조를 줄여요.',
      eye: ['eye', 'wing', .2], liner: ['basic', 0], blush: ['#d99a90', 'diagonal', 0.15, 0], lip: ['#a0463c', 'blur', .62], lipMuted: .1, lipGloss: 0, noseCleft: 0.38, noseShape: 'sculpted', shadingShape: 'sculpt',  cleft: 0.4, shading: 0.65, nose: 0.56, highlight: ['bone', .2], highlightHex: '#f2e3d6', brow: 'M17_natural_angular' },
    { name: '윤곽', description: '광대 밑 사선 음영과 코끝·턱끝의 작은 입체감, 말린 장미 매트 립. 넓은 골격은 강조를 줄여요.',
      eye: ['eye', 'basic', .18], liner: ['basic', 0], blush: ['#d99a90', 'diagonal', 0.12, 0], lip: ['#9b5058', 'blur', .55], lipMuted: .15, lipGloss: 0, noseCleft: 0.28, noseShape: 'sculpted', shadingShape: 'sculpt',  cleft: 0.32, shading: 0.56, nose: 0.5, highlight: ['bone', .26], highlightHex: '#f2e3d6', brow: 'M13_textured_angular' },
    { name: '스테이지', description: '조명 아래서도 생기 있게, 숱 많은 눈썹과 윤기 있는 베리 립.',
      eye: ['eye', 'smoky', .25], liner: ['basic', 0], blush: ['#e3a39a', 'wide', 0.18, 0], lip: ['#a63a56', 'gradient', .68], lipGloss: 0.35, noseCleft: 0.3, noseShape: 'tip', shadingShape: 'chin',  cleft: 0.3, shading: 0.4, nose: 0.46, highlight: ['tzone', .18], highlightHex: '#f2e3d6', brow: 'M18_dense_straight' },
  ],
}

// 피부톤 분석(/skin/tone) → 메이크업 축: 밝기, 쿠션 범위 문구 → 호수 가운데값·베이스
// 밝기는 ITA°로 다시 나눔: 백엔드 '밝은 편'(41 초과, 피부과 분류)이 휴대폰 사진에선 거의 전부라 60 초과만 밝은 피부
// (테스트 14장 ITA 54~82), 28 이하 어두운 피부는 피부과 분류 그대로. ITA 없으면 백엔드 단계 그대로
const MAKEUP_LIGHT_ITA = 60, MAKEUP_DEEP_ITA = 28
export function brightnessFromAnalysis(level: 'bright' | 'medium' | 'deep', ita?: number): Brightness {
  if (typeof ita === 'number' && Number.isFinite(ita)) return ita > MAKEUP_LIGHT_ITA ? 'light' : ita > MAKEUP_DEEP_ITA ? 'medium' : 'deep'
  return level === 'bright' ? 'light' : level
}
export function cushionFromAnalysis(text: string | null | undefined): Cushion | undefined {
  if (!text) return undefined
  const range = text.match(/(\d+)\s*~\s*(\d+)\s*호/), above = text.match(/(\d+)\s*호\s*이상/)
  const shade = range ? (Number(range[1]) + Number(range[2])) / 2 : above ? Number(above[1]) + 1 : null
  if (shade === null) return undefined
  const base: CushionBase = text.includes('핑크') ? 'pink' : text.includes('황조') || text.includes('옐로') ? 'yellow' : 'neutral'
  return { shade, base }
}
export function faceShapeFromAnalysis(value: string | null | undefined): FaceShape | null {
  if (!value) return null
  return FACE_SHAPES.find(s => s.label === value || s.id === value || (s.id === 'diamond' && value === '다이아몬드'))?.id ?? null
}
export function recommendMakeupLooks(profile: MakeupProfile & { faceShape: FaceShape }, requested: MakeupOccasion = 'daily'): MakeupLook[] {
  const occasion = MAKEUP_OCCASIONS.some(o => o.id === requested) ? requested : 'daily'
  const placement = PLACEMENT[profile.faceShape], base = TONE_BASE[profile.tone]
  const palettes = TONE_PALETTES[profile.tone], shade = base.shade
  // 색 결정: 팔레트 칸이면 톤 팔레트의 그 부위 색, '#hex'면 레퍼런스 색을 톤 쪽으로 옮김 → 둘 다 밝기 조정
  const color = (ref: ColorRef, key: 'eyeshadow' | 'blush' | 'lip') => {
    // 레퍼런스 색은 뉴트럴 기준 그대로, 쿨은 색상 이동 (립은 레퍼런스 차이를 살리려고 절반만), 웜은 라이트 코랄·베이지로
    const raw = ref.startsWith('#') ? ref : palettes[ref as PaletteId][key]
    const toned = profile.tone === 'warm' ? warmHex(raw, key) : ref.startsWith('#') ? toneHex(raw, profile.tone, profile.tone === 'neutral' ? 0 : key === 'lip' ? .2 : .4) : raw
    return shiftHex(toned, profile.brightness)
  }
  const male = profile.sex === 'male'
  const eyeAmt = (v: number) => male ? v : Math.min(1, v * FEMALE_EYE_BOOST)
  // 립: 톤별 지정색 > 레퍼런스/팔레트 색, 그다음 베이지·탁기 섞기
  const pale = Math.min(1, Math.max(0, profile.lipPale ?? 0))
  const lipHex = (r: Recipe) => {
    let hex = r.lipBy?.[profile.tone] ? shiftHex(r.lipBy[profile.tone]!, profile.brightness) : color(r.lip[0], 'lip')
    // 창백한 입술엔 베이지를 덜 섞음 (베이지가 원래 옅은 입술을 더 창백하게 만듦)
    if (r.lipBeige) hex = mixHex(hex, LIP_BEIGE[profile.tone], r.lipBeige * (1 - LIP_PALE_BEIGE * pale))
    const tint = r.lipTint?.[profile.tone]
    if (tint && pale) hex = mixHex(hex, shiftHex(tint, profile.brightness), LIP_PALE_TINT * pale)
    if (pale) hex = saturateHex(hex, 1 + LIP_PALE_SAT * Math.min(1, pale * 1.5))
    if (r.lipMuted) hex = mixHex(hex, LIP_MUTED, r.lipMuted)
    return hex
  }
  const toneLabel = TONES.find(t => t.id === profile.tone)!.label
  return (male ? MALE : FEMALE)[occasion].map((r, index) => {
    const [, blushShape, blushAmount, glow] = r.blush
    // 스모키·아주 진한 라인은 짙은 색, 나머지는 브라운
    const defined = r.eye[1] === 'smoky' || r.liner[1] >= .8
    const linerColor = defined ? base.liner[0] : base.liner[1]
    const mood = male ? '그루밍' : r.lip[0].startsWith('#') ? `${toneLabel} 톤` : palettes[r.lip[0] as PaletteId].name
    return { id: `${male ? 'm' : 'f'}-${occasion}-${index}`, name: r.name, mood, description: r.description, occasion, lashes: r.lashes ?? 'none', brow: r.brow, settings: {
      ...DEFAULT_MAKEUP,
      blush: { on: blushAmount > 0, hex: r.blushBy?.[profile.tone] ? shiftHex(r.blushBy[profile.tone]!, profile.brightness) : color(r.blush[0], 'blush'), amount: blushAmount, shape: blushShape, glow, tip: r.blushTip },
      eyeshadow: { on: r.eye[2] > 0, hex: color(r.eye[0], 'eyeshadow'), amount: eyeAmt(r.eye[2]), shape: r.eye[1], shimmer: r.shimmer },
      shadowPoint: r.point ? { on: r.point[2] > 0, hex: color(r.point[0], 'eyeshadow'), amount: eyeAmt(r.point[2]), shape: r.point[1] } : DEFAULT_MAKEUP.shadowPoint,
      skin: { on: true, hex: cushionHex(profile.cushion ?? { shade: BRIGHT_SHADE[profile.brightness], base: TONE_CUSHION[profile.tone] }), amount: r.skin ?? (male ? .7 : .55), shape: 'cushion', beard: male ? .9 : 0 },
      aegyo: r.aegyo ? { on: true, hex: AEGYO_COLOR[profile.tone], amount: r.aegyo, shape: r.aegyoShape ?? 'soft' } : DEFAULT_MAKEUP.aegyo,
      underShadow: r.under ? { on: r.under[2] > 0, hex: color(r.under[0], 'eyeshadow'), amount: eyeAmt(r.under[2]), shape: r.under[1] } : DEFAULT_MAKEUP.underShadow,
      eyeliner: { on: r.liner[1] > 0, hex: linerColor, amount: eyeAmt(r.liner[1]), shape: r.liner[0] },
      lip: { on: r.lip[2] > 0, hex: lipHex(r), amount: Math.min(1, r.lip[2] * (1 + LIP_PALE_BOOST * Math.min(1, pale * 1.5))), shape: r.lip[1], soft: r.lipSoft, gloss: r.lipGloss },
      shading: { on: r.shading > 0, hex: shade, amount: r.shading, shape: r.shadingShape ?? placement.shading, cleft: r.cleft },
      noseShading: { on: r.nose > 0, hex: shade, amount: r.nose, shape: r.noseShape ?? 'soft', noseCleft: r.noseCleft },
      // 블러셔 광을 켠 룩은 하이라이터를 줄여 겹치지 않게
      highlight: { on: r.highlight[1] > 0, hex: r.highlightHex ?? base.highlight, amount: r.highlight[1] * (1 - glow * .4), shape: r.highlight[0] ?? placement.highlight },
    } }
  })
}

// 직접 꾸미기: 부위별 추천 색 칩 (피부 톤 팔레트 5칸 + 밝기 보정, 첫 칸이 켤 때 기본색)
export function customSwatches(profile: Pick<MakeupProfile, 'tone' | 'brightness'>): Record<MakeupPart, string[]> {
  const palettes = Object.values(TONE_PALETTES[profile.tone]), base = TONE_BASE[profile.tone]
  const pick = (key: 'eyeshadow' | 'blush' | 'lip') => palettes.map(p => shiftHex(p[key], profile.brightness))
  const shades = [base.shade, ...(['warm', 'neutral', 'cool'] as const).filter(t => t !== profile.tone).map(t => TONE_BASE[t].shade)]
  return {
    skin: [], eyeshadow: pick('eyeshadow'), shadowPoint: pick('eyeshadow').reverse(), underShadow: pick('eyeshadow'),
    aegyo: [AEGYO_COLOR[profile.tone], ...pick('eyeshadow').slice(0, 2)], blush: pick('blush'), lip: pick('lip'),
    eyeliner: [base.liner[1], base.liner[0], '#1c1716'], shading: shades, noseShading: shades,
    highlight: [base.highlight, '#f6d9a2', '#f2e3d6'],
  }
}
