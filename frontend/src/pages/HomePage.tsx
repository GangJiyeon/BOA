import { useEffect, useState } from 'react'
import { getHealth, type Health } from '../api/health'

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
      <h1>BOA</h1>
      {error && <p>백엔드 연결 실패: {error}</p>}
      {!error && !health && <p>백엔드 확인 중...</p>}
      {health && (
        <ul>
          <li>API: {health.status}</li>
          <li>DB: {health.db ? '연결됨' : '연결 실패'}</li>
          <li>S3: {health.s3 ? '설정됨' : '미설정'}</li>
        </ul>
      )}
    </main>
  )
}
