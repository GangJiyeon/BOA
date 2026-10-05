import { useEffect, useState } from 'react'
import { getHealth, type Health } from '../api/health'
import CosmeticPreview from '../components/CosmeticPreview'

export default function HomePage() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <main>
      <header className="site-header"><h1>BOA<span> Beauty, on your terms.</span></h1></header>
      {error && <p>백엔드 연결 실패: {error}</p>}
      {!error && !health && <p>백엔드 확인 중...</p>}
      {health && (
        <ul className="health-status">
          <li>API: {health.status}</li>
          <li>DB: {health.db ? '연결됨' : '연결 실패'}</li>
          <li>S3: {health.s3 ? '설정됨' : '미설정'}</li>
        </ul>
      )}
      <CosmeticPreview />
    </main>
  )
}
