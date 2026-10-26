import type { PreviewResponse, ProductCategory } from '../api/cosmetics'
import type { FaceAnalysis, HairResult } from '../api/hair'
import type { SkinAnalysis } from '../api/skin'

// 이번 이용 중 완료된 결과만 보관한다. 서버 저장/회원 기록 계약이 아니다.
export type CosmeticSessionResult = {
  response: PreviewResponse
  inputMode: 'photo' | 'analysis' | 'development'
  analysis: SkinAnalysis | null
  category: ProductCategory | null
}

export type HairSessionResult = {
  result: HairResult
  analysis: FaceAnalysis
  // AI 스튜디오 합성용 정면 사진 (첫 장), 브라우저 메모리에만 보관
  photo: File
}
