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
  console.log('API client: 8 checks passed')
} finally { globalThis.fetch = savedFetch }
