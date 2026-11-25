import { useState } from 'react'

// 이번 이용 세션의 정면 사진 (브라우저 메모리만, 서버 저장 없음)
// 헤어·AI Studio·메이크업끼리만 공유 (피부는 근접 촬영이라 따로 씀)
export type SessionPhotoProps = {
  sessionPhoto?: File | null
  // next: 새 사진(삭제면 null), prev: 화면에 있던 사진
  onPhoto?: (next: File | null, prev: File | null) => void
}

// 세션 사진이 바뀐 순간에만 받아 씀 → 화면에서 직접 지운 뒤 다시 채워지는 일 없음
// 이미 사진이 있는 화면은 유지 (결과·진행 중 작업 보호)
export function useAdoptSessionPhoto(sessionPhoto: File | null | undefined, empty: boolean, adopt: (file: File) => void) {
  const [seen, setSeen] = useState<File | null>(null)
  const current = sessionPhoto ?? null
  if (current !== seen) {
    setSeen(current)
    if (current && empty) adopt(current)
  }
}
