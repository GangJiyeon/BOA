// 공유 주소로 이동하지 않고 토큰만 읽어 기존 BOA API에 전달한다.
export function resultToken(input: string): string {
  const value = input.trim()
  if (/^[A-Za-z0-9_-]+$/.test(value)) return value
  try {
    const url = new URL(value, window.location.origin)
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error()
    const [path, query] = url.hash.slice(1).split('?')
    if (path !== '/results') throw new Error()
    const tokens = new URLSearchParams(query).getAll('token')
    if (tokens.length !== 1 || !/^[A-Za-z0-9_-]+$/.test(tokens[0])) throw new Error()
    return tokens[0]
  } catch {
    throw new Error('결과 토큰 또는 BOA에서 복사한 결과 공유 주소를 입력해 주세요.')
  }
}
