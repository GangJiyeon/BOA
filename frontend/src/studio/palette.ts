// 32색 프리셋 (사진 1장·스타일 2개로 맞춘 값)
// base: mid = 어두운 갈색(L 30 미만 색), brown = 중간 갈색(L 30~52), light = 밝은 애쉬 플래티넘(그 밖)
// 세 베이스 모두 Flash 한 번에 생성, 베이스에서 멀리 칠할수록 외곽·떡짐이 드러나 가장 가까운 베이스 사용
// 지정 안 한 값은 DEFAULT_TUNING
// 카키·올리브·민트·코랄·골드·라벤더·애쉬퍼플·블루그레이는 칠한 느낌이 강해 뺌
export type HairBase = 'light' | 'brown' | 'mid'
export type HairTuning = { lOff: number; chroma: number; tex: number; vari: number }
export type HairColor = Partial<HairTuning> & { name: string; hex: string; base: HairBase }

export const DEFAULT_TUNING: HairTuning = { lOff: 0, chroma: 1, tex: 1, vari: 0.4 }

export const PALETTE: { group: string; colors: HairColor[] }[] = [
  { group: '블랙 · 브라운', colors: [
    { name: '흑발', hex: '#1c1714', base: 'mid', tex: 1.4, vari: 0.3 },
    { name: '블루블랙', hex: '#1d2230', base: 'mid', tex: 1.4, vari: 0.3, chroma: 0.6 },
    { name: '소프트블랙', hex: '#2e2622', base: 'mid', tex: 1.3, vari: 0.3 },
    { name: '다크브라운', hex: '#3b2a20', base: 'mid', tex: 1.15, vari: 0.3 },
    { name: '초코브라운', hex: '#5a3a28', base: 'mid', tex: 0.8, vari: 0.3, chroma: 0.85 },
    { name: '매트브라운', hex: '#5e4838', base: 'brown', tex: 0.8, vari: 0.3, chroma: 0.85 },
    { name: '모카브라운', hex: '#6a4a38', base: 'brown', tex: 0.8, vari: 0.3, chroma: 0.8 },
    { name: '밀크브라운', hex: '#8a6a50', base: 'brown', tex: 0.7, vari: 0.3, chroma: 0.8 },
  ] },
  { group: '애쉬 · 블론드', colors: [
    { name: '다크애쉬', hex: '#4a4440', base: 'mid', tex: 0.8, vari: 0.3, chroma: 0.8 },
    { name: '애쉬브라운', hex: '#6b5a4e', base: 'brown', tex: 0.7, vari: 0.3, chroma: 0.9 },
    { name: '밀크티베이지', hex: '#a08670', base: 'light', chroma: 0.75, lOff: -2 },
    { name: '애쉬베이지', hex: '#9a8a7a', base: 'light', chroma: 0.7, lOff: -2 },
    { name: '베이지블론드', hex: '#c8a77e', base: 'light', chroma: 0.68, lOff: -3, vari: 0.3 },
    { name: '허니블론드', hex: '#c08a4a', base: 'light', chroma: 0.65, lOff: -4 },
    { name: '플래티넘블론드', hex: '#d4c0a0', base: 'light', chroma: 0.6, lOff: -6, tex: 0.9 },
    { name: '화이트블론드', hex: '#e0d8c8', base: 'light', chroma: 0.5, lOff: -8, tex: 0.85 },
  ] },
  { group: '레드 · 핑크', colors: [
    { name: '레드브라운', hex: '#6e2f22', base: 'mid', tex: 0.8, vari: 0.3, chroma: 0.65, lOff: -3 },
    { name: '체리레드', hex: '#7a1e24', base: 'mid', tex: 0.8, vari: 0.3, chroma: 0.7, lOff: -3 },
    { name: '와인', hex: '#5a1f2c', base: 'mid', tex: 1.0, vari: 0.3, chroma: 0.8 },
    { name: '버건디', hex: '#4a1a26', base: 'mid', tex: 1.1, vari: 0.3, chroma: 0.8 },
    { name: '카퍼', hex: '#8a3e22', base: 'brown', tex: 0.7, vari: 0.3, chroma: 0.62, lOff: -4 },
    { name: '오렌지브라운', hex: '#8a4a28', base: 'brown', tex: 0.7, vari: 0.3, chroma: 0.6, lOff: -4 },
    { name: '로즈브라운', hex: '#7a3e4e', base: 'brown', tex: 0.8, vari: 0.3, chroma: 0.75, lOff: -2 },
    { name: '핑크브라운', hex: '#8a5552', base: 'brown', tex: 0.7, vari: 0.3, chroma: 0.72, lOff: -3 },
    { name: '애쉬핑크', hex: '#b08a90', base: 'light', chroma: 0.65, lOff: -4 },
    { name: '피치핑크', hex: '#d08a80', base: 'light', chroma: 0.6, lOff: -6 },
    { name: '베이비핑크', hex: '#e0a0aa', base: 'light', chroma: 0.6, lOff: -6 },
  ] },
  { group: '쿨톤', colors: [
    { name: '네이비', hex: '#232a40', base: 'mid', tex: 1.3, vari: 0.3, chroma: 0.6 },
    { name: '딥퍼플', hex: '#3e2a4a', base: 'mid', tex: 1.1, vari: 0.3, chroma: 0.75 },
    { name: '애쉬블루', hex: '#7a8ea0', base: 'light', chroma: 0.6, lOff: -4 },
    { name: '애쉬그레이', hex: '#8c8a88', base: 'light', chroma: 0.8, lOff: -4, tex: 0.9 },
    { name: '실버', hex: '#b8b8bc', base: 'light', chroma: 0.6, lOff: -6, tex: 0.85 },
  ] },
]
