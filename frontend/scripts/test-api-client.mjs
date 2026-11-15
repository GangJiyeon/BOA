import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import ts from 'typescript'
const source = await fs.readFile(new URL('../src/api/client.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } })
const { api, ApiError } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
const savedFetch = globalThis.fetch
let captured
try {
  globalThis.fetch = async (url, init) => { captured = {url, init}; return new Response('{}') }
  await api('/test', { method: 'POST', body: JSON.stringify({score: 20}) })
  assert.equal(captured.url, '/api/test')
  assert.equal(captured.init.headers.get('Content-Type'), 'application/json')
  const form = new FormData(); form.append('file', new Blob(['image']), 'face.png')
  await api('/skin/analyses/debug', { method: 'POST', body: form })
  assert.equal(captured.init.headers.has('Content-Type'), false)
  assert.equal(captured.init.body, form)
  const controller = new AbortController()
  await api('/test', {signal: controller.signal})
  assert.equal(captured.init.signal, controller.signal)
  globalThis.fetch = async () => new Response(JSON.stringify({detail:{code:'FACE_NOT_FOUND',message:'얼굴을 찾지 못했습니다'}}), {status:400})
  await assert.rejects(api('/test'), err => err instanceof ApiError && err.status === 400 && err.message === '얼굴을 찾지 못했습니다')
  globalThis.fetch = async () => new Response(JSON.stringify({detail:[{loc:['body','score'],msg:'정수 필요'}]}), {status:422})
  await assert.rejects(api('/test'), /body.score: 정수 필요/)
  globalThis.fetch = async () => new Response(JSON.stringify({detail:'추천 조건 오류'}), {status:422})
  await assert.rejects(api('/test'), /추천 조건 오류/)
  assert.equal(captured.init.credentials, 'same-origin')
  globalThis.fetch = async () => new Response(null, {status:204})
  assert.equal(await api('/auth/logout', {method:'POST'}), undefined)
  assert.equal(await api('/kiosk/session', {method:'DELETE'}), undefined)
  globalThis.fetch = async () => new Response('<html>proxy failed</html>', {status:502})
  await assert.rejects(api('/test'), err => err instanceof ApiError && err.status === 502 && err.message.includes('서버에서 요청'))
  globalThis.fetch = async () => new Response(JSON.stringify({detail:[null, {loc:'body',msg:'입력 오류'}]}), {status:422})
  await assert.rejects(api('/test'), /입력: 입력 오류/)
  globalThis.fetch = async () => new Response('<html>wrong server</html>')
  await assert.rejects(api('/test'), /서버 응답 형식/)
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch') }
  await assert.rejects(api('/test'), err => err instanceof ApiError && err.status === 0 && err.message.includes('서버에 연결'))
  const cancelled = new DOMException('cancelled', 'AbortError')
  globalThis.fetch = async () => { throw cancelled }
  await assert.rejects(api('/test'), err => err === cancelled)
  const unauthorized = () => new Response(JSON.stringify({detail:'만료'}), {status:401})
  let refreshes = 0
  let calls = 0
  let releaseRefresh
  globalThis.fetch = async (url) => {
    if (url === '/api/auth/refresh') {
      refreshes++
      await new Promise(resolve => { releaseRefresh = resolve })
      return new Response(null, {status:204})
    }
    calls++
    return calls <= 2 ? unauthorized() : new Response('{"ok":true}')
  }
  const first = api('/me')
  const second = api('/guest/quota')
  await new Promise(resolve => setTimeout(resolve, 0))
  assert.equal(refreshes, 1)
  releaseRefresh()
  assert.deepEqual(await Promise.all([first, second]), [{ok:true}, {ok:true}])
  assert.equal(calls, 4)

  calls = 0; refreshes = 0
  globalThis.fetch = async url => {
    if (url === '/api/auth/refresh') { refreshes++; return unauthorized() }
    calls++; return unauthorized()
  }
  await assert.rejects(api('/me'), err => err.status === 401 && err.message.includes('다시 로그인'))
  assert.equal(refreshes, 1)
  assert.equal(calls, 1)
  await assert.rejects(api('/auth/signup', {method:'POST'}), err => err.status === 401)
  assert.equal(refreshes, 1)

  calls = 0; refreshes = 0
  globalThis.fetch = async url => {
    if (url === '/api/auth/refresh') { refreshes++; return new Response(null, {status:204}) }
    calls++; return unauthorized()
  }
  await assert.rejects(api('/me'), err => err.status === 401)
  assert.equal(refreshes, 1)
  assert.equal(calls, 2) // 재시도도 401이면 반복하지 않는다.

  calls = 0
  const aborted = new AbortController()
  globalThis.fetch = async url => {
    if (url === '/api/auth/refresh') {
      aborted.abort()
      return new Response(null, {status:204})
    }
    calls++; return unauthorized()
  }
  await assert.rejects(api('/me', {signal:aborted.signal}), err => err.name === 'AbortError')
  assert.equal(calls, 1)
  // 갱신 완료 뒤 늦게 도착한 401도 기존 갱신 결과를 사용한다.
  let lateResponse
  calls = 0; refreshes = 0
  globalThis.fetch = async (url, init) => {
    if (url === '/api/auth/refresh') { refreshes++; return new Response(null, {status:204}) }
    if (url === '/api/late' && !lateResponse) return new Promise(resolve => { lateResponse = resolve })
    calls++
    if (url === '/api/upload' && calls === 1) return unauthorized()
    if (url === '/api/upload') assert.equal(init.body, form)
    return new Response('{}')
  }
  const late = api('/late')
  await api('/upload', {method:'POST', body:form})
  lateResponse(unauthorized())
  await late
  assert.equal(refreshes, 1)

  const savedWindow = globalThis.window
  const events = new EventTarget()
  globalThis.window = events
  let expirations = 0
  events.addEventListener('boa:session-expired', () => expirations++)
  try {
    globalThis.fetch = async () => unauthorized()
    await assert.rejects(api('/me'), err => err.status === 401)
    assert.equal(expirations, 1)
    globalThis.fetch = async url => url === '/api/auth/refresh'
      ? new Response(null, {status:503}) : unauthorized()
    await assert.rejects(api('/me'), err => err.status === 503)
    assert.equal(expirations, 1) // 일시적인 서버 오류는 로그아웃시키지 않는다.
  } finally {
    if (savedWindow === undefined) delete globalThis.window
    else globalThis.window = savedWindow
  }
  console.log('API client: existing checks and automatic refresh scenarios passed')
} finally { globalThis.fetch = savedFetch }
