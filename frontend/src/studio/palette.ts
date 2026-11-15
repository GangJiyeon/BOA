// 32색 프리셋 (tex·vari는 사진 1장·스타일 2개로 맞춘 값)
// 색은 renderColor가 머리 평균을 목표 hex에 맞춤 → 채도·밝기 깎는 보정 없음
// base: 세 베이스 중 없을 때 대체용, 실제 베이스는 pickBase가 사진별 머리 밝기로 고름
// (mid = 어두운 갈색, brown = 중간 갈색, light = 펄 블론드)
// 지정 안 한 값은 DEFAULT_TUNING
// 카키·올리브·민트·코랄·골드·라벤더·애쉬퍼플·블루그레이는 칠한 느낌이 강해 뺌
export type HairBase = 'light' | 'brown' | 'mid'
export type HairTuning = { lOff: number; chroma: number; tex: number; vari: number }
// lockBase: 자동 선택(pickBase) 대신 base 고정 (brown에서 칠하면 눈썹까지 물들어 부자연스러운 애쉬·금발 계열,
// brown(L 18~32)에서 크게 밝혀 칙칙해지는 밝은·고채도 색: 밀크브라운·밀크티베이지·카퍼·오렌지브라운·핑크브라운·피치핑크)
export type HairColor = Partial<HairTuning> & { name: string; hex: string; base: HairBase; lockBase?: boolean }

export const DEFAULT_TUNING: HairTuning = { lOff: 0, chroma: 1, tex: 1, vari: 0.4 }

export const PALETTE: { group: string; colors: HairColor[] }[] = [
  { group: '블랙 · 브라운', colors: [
    { name: '흑발', hex: '#1c1714', base: 'mid', tex: 1.4, vari: 0.3 },
    { name: '블루블랙', hex: '#1d2230', base: 'mid', tex: 1.4, vari: 0.3 },
    { name: '소프트블랙', hex: '#2e2622', base: 'mid', tex: 1.3, vari: 0.3 },
    { name: '다크브라운', hex: '#3b2a20', base: 'mid', tex: 1.15, vari: 0.3 },
    { name: '초코브라운', hex: '#5a3a28', base: 'mid', tex: 0.8, vari: 0.3 },
    { name: '매트브라운', hex: '#5e4838', base: 'brown', tex: 0.8, vari: 0.3 },
    { name: '모카브라운', hex: '#6a4a38', base: 'brown', tex: 0.8, vari: 0.3 },
    { name: '밀크브라운', hex: '#8a6a50', base: 'light', lockBase: true, tex: 0.7, vari: 0.3 },
  ] },
  { group: '애쉬 · 블론드', colors: [
    { name: '다크애쉬', hex: '#4a4440', base: 'mid', tex: 0.8, vari: 0.3 },
    { name: '애쉬브라운', hex: '#6b5a4e', base: 'brown', tex: 0.7, vari: 0.3 },
    { name: '밀크티베이지', hex: '#a08670', base: 'light', lockBase: true },
    { name: '애쉬베이지', hex: '#9a8a7a', base: 'light', lockBase: true },
    { name: '베이지블론드', hex: '#c8a77e', base: 'light', vari: 0.3 },
    { name: '허니블론드', hex: '#c08a4a', base: 'light', lockBase: true },
    { name: '플래티넘블론드', hex: '#d4c0a0', base: 'light', tex: 0.9 },
    { name: '화이트블론드', hex: '#e0d8c8', base: 'light', tex: 0.85 },
  ] },
  { group: '레드 · 핑크', colors: [
    { name: '레드브라운', hex: '#6e2f22', base: 'mid', tex: 0.8, vari: 0.3 },
    { name: '체리레드', hex: '#7a1e24', base: 'mid', tex: 0.8, vari: 0.3 },
    { name: '와인', hex: '#5a1f2c', base: 'mid', tex: 1.0, vari: 0.3 },
    { name: '버건디', hex: '#4a1a26', base: 'mid', tex: 1.1, vari: 0.3 },
    { name: '카퍼', hex: '#8a3e22', base: 'light', lockBase: true, tex: 0.7, vari: 0.3 },
    { name: '오렌지브라운', hex: '#8a4a28', base: 'light', lockBase: true, tex: 0.7, vari: 0.3 },
    { name: '로즈브라운', hex: '#7a3e4e', base: 'brown', tex: 0.8, vari: 0.3 },
    { name: '핑크브라운', hex: '#8a5552', base: 'light', lockBase: true, tex: 0.7, vari: 0.3 },
    { name: '애쉬핑크', hex: '#b08a90', base: 'light', lockBase: true },
    { name: '피치핑크', hex: '#d08a80', base: 'light', lockBase: true },
    { name: '베이비핑크', hex: '#e0a0aa', base: 'light' },
  ] },
  { group: '쿨톤', colors: [
    { name: '네이비', hex: '#232a40', base: 'mid', tex: 1.3, vari: 0.3 },
    { name: '딥퍼플', hex: '#3e2a4a', base: 'mid', tex: 1.1, vari: 0.3 },
    { name: '애쉬블루', hex: '#7a8ea0', base: 'light', lockBase: true },
    { name: '애쉬그레이', hex: '#8c8a88', base: 'light', lockBase: true, tex: 0.9 },
    { name: '실버', hex: '#b8b8bc', base: 'light', tex: 0.85 },
  ] },
]
