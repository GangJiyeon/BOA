import { showDevTools } from '../utils/uiFeatures'
import type { SkinToneResult } from '../api/skin'
import type { HairColorRecommendation } from '../studio/hairColorRecommendations'

type Props = {
  result: SkinToneResult
  recommendations: HairColorRecommendation[]
  basis?: string
  source: 'hair-recommendation' | 'ai-studio'
}

export default function SkinToneSummary({ result, recommendations, basis, source }: Props) {
  function downloadLog() {
    const exportedAt = new Date().toISOString()
    const log = {
      schema_version: 1,
      exported_at: exportedAt,
      source,
      skin_tone: {
        brightness_label: result.brightness_label,
        undertone: result.undertone,
        undertone_label: result.undertone_label,
        confidence: result.confidence,
        cushion: result.palette.cushion,
        raw: result.raw,
      },
      hair_color: { basis: basis ?? null, recommendations },
    }
    const blob = new Blob([JSON.stringify(log, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'boa-skin-tone-' + exportedAt.replace(/[:.]/g, '-') + '.json'
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return <div aria-label="피부톤 분석 결과" role="group">
    <p className="input-note">
      <strong>피부톤 분석 결과</strong>{' · '}피부 밝기 {result.brightness_label}
      {' · '}언더톤 {result.undertone_label || '판정 정보 없음'}
    </p>
    <p className="input-note"><strong>쿠션 추천 호수</strong>{' · '}{result.palette.cushion}</p>
    {result.confidence === 'low' && <p className="input-note">피부톤 판정이 불확실해요. 결과는 참고용으로 봐 주세요.</p>}
    {showDevTools && <button type="button" className="secondary" onClick={downloadLog}>테스트 로그 다운로드 (JSON)</button>}
  </div>
}
