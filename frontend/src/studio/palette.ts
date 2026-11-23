// 32색 프리셋 (tex·vari는 사진 1장·스타일 2개로 맞춘 값)
// 색은 renderColor가 머리 평균을 목표 hex에 맞춤 → 채도·밝기 깎는 보정 없음
// base는 프리셋의 기존 메타데이터. 스튜디오는 응답에 있는 베이스 한 장을 사용.
export type HairBase = 'light' | 'brown' | 'mid'
export type HairTuning = { lOff: number; chroma: number; tex: number; vari: number }
export type HairColor = Partial<HairTuning> & { name: string; hex: string; base: HairBase; lockBase?: boolean }

export const DEFAULT_TUNING: HairTuning = { lOff: 0, chroma: 1, tex: 1, vari: 0.4 }

export const PALETTE: { group: string; colors: HairColor[] }[] = [
  { group: '블랙', colors: [
    { name: '흑발', hex: '#1c1714', base: 'mid', tex: 1.4, vari: 0.3 },
    { name: '블루블랙', hex: '#1d2230', base: 'mid', tex: 1.4, vari: 0.3 },
    { name: '애쉬블랙', hex: '#2a2a2c', base: 'mid', tex: 1.3, vari: 0.3 },
    { name: '소프트블랙', hex: '#2e2622', base: 'mid', tex: 1.3, vari: 0.3 },
  ] },
  { group: '브라운', colors: [
    { name: '다크브라운', hex: '#3b2a20', base: 'mid', tex: 1.15, vari: 0.3 },
    { name: '다크초코', hex: '#3a2418', base: 'mid', tex: 1.15, vari: 0.3 },
    { name: '초코브라운', hex: '#5a3a28', base: 'mid', tex: 0.8, vari: 0.3 },
    { name: '코코아브라운', hex: '#5e3e30', base: 'brown', tex: 0.8, vari: 0.3 },
    { name: '모카브라운', hex: '#6a4a38', base: 'brown', tex: 0.8, vari: 0.3 },
    { name: '카라멜브라운', hex: '#6e4a30', base: 'brown', tex: 0.8, vari: 0.3 },
    { name: '매트브라운', hex: '#5e4838', base: 'brown', tex: 0.8, vari: 0.3 },
    { name: '밀크브라운', hex: '#6e5240', base: 'brown', tex: 0.8, vari: 0.3 },
  ] },
  { group: '애쉬', colors: [
    { name: '다크애쉬', hex: '#4a4440', base: 'mid', tex: 0.8, vari: 0.3 },
    { name: '매트애쉬', hex: '#555048', base: 'brown', tex: 0.7, vari: 0.3 },
    { name: '애쉬브라운', hex: '#6b5a4e', base: 'brown', tex: 0.7, vari: 0.3 },
    { name: '애쉬그레이브라운', hex: '#5a5654', base: 'brown', tex: 0.7, vari: 0.3 },
    { name: '카키브라운', hex: '#5a5040', base: 'brown', tex: 0.7, vari: 0.3 },
  ] },
  { group: '레드', colors: [
    { name: '레드브라운', hex: '#6e2f22', base: 'mid', tex: 0.8, vari: 0.3 },
    { name: '마호가니', hex: '#5c2a22', base: 'mid', tex: 0.9, vari: 0.3 },
    { name: '카퍼브라운', hex: '#6e3a22', base: 'brown', tex: 0.8, vari: 0.3 },
    { name: '오렌지브라운', hex: '#6e4026', base: 'brown', tex: 0.8, vari: 0.3 },
    { name: '체리레드', hex: '#7a1e24', base: 'mid', tex: 0.8, vari: 0.3 },
    { name: '다크체리', hex: '#5a1a20', base: 'mid', tex: 1.0, vari: 0.3 },
    { name: '와인', hex: '#5a1f2c', base: 'mid', tex: 1.0, vari: 0.3 },
    { name: '버건디', hex: '#4a1a26', base: 'mid', tex: 1.1, vari: 0.3 },
  ] },
  { group: '핑크 · 퍼플 · 블루', colors: [
    { name: '로즈브라운', hex: '#7a3e4e', base: 'brown', tex: 0.8, vari: 0.3 },
    { name: '핑크브라운', hex: '#6e4446', base: 'brown', tex: 0.8, vari: 0.3 },
    { name: '플럼', hex: '#4e2a3e', base: 'mid', tex: 1.0, vari: 0.3 },
    { name: '딥퍼플', hex: '#3e2a4a', base: 'mid', tex: 1.1, vari: 0.3 },
    { name: '퍼플블랙', hex: '#2e2236', base: 'mid', tex: 1.3, vari: 0.3 },
    { name: '네이비', hex: '#232a40', base: 'mid', tex: 1.3, vari: 0.3 },
    { name: '애쉬블루', hex: '#3a4250', base: 'mid', tex: 1.1, vari: 0.3 },
  ] },
]
