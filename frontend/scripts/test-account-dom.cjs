// BOA_TEST_MODULES points to a folder containing the test-only esbuild and jsdom packages.
const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), assert = require('node:assert/strict')
const modules = process.env.BOA_TEST_MODULES
if (!modules) throw new Error('Set BOA_TEST_MODULES to a node_modules folder containing esbuild and jsdom')
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'boa-account-dom-'))
const frontend = path.resolve(__dirname, '..'), appModules = path.join(frontend, 'node_modules')
fs.writeFileSync(path.join(dir, 'entry.tsx'), `export {default as React,act} from 'react';export {createRoot} from 'react-dom/client';export {default as AccountPage} from ${JSON.stringify(path.join(frontend, 'src/pages/AccountPage'))};`)
require(path.join(modules, 'esbuild')).buildSync({
  entryPoints: [path.join(dir, 'entry.tsx')], outfile: path.join(dir, 'bundle.cjs'), bundle: true,
  platform: 'browser', format: 'cjs', jsx: 'automatic', nodePaths: [appModules],
  define: { 'import.meta.env.VITE_GOOGLE_CLIENT_ID': 'undefined', 'process.env.NODE_ENV': '"development"' },
  alias: { react: path.join(appModules, 'react'), 'react-dom': path.join(appModules, 'react-dom') },
})
const { JSDOM } = require(path.join(modules, 'jsdom'))
const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/#/start' })
global.window = dom.window; global.document = dom.window.document; global.IS_REACT_ACT_ENVIRONMENT = true
const { React, act, createRoot, AccountPage } = require(path.join(dir, 'bundle.cjs'))
const initialConsents = [
  { type: 'SERVICE', required: true, agreed: true, version: 'v1', updated_at: null },
  { type: 'PHOTO_STORAGE', required: false, agreed: false, version: null, updated_at: null },
  { type: 'MARKETING', required: false, agreed: true, version: 'v1', updated_at: null },
]
let consents, loadFails = false, changeFails = false, deleteFails = false, pendingDelete, releaseDelete
let requests = [], logoutCalls = 0, actorChanges = 0, result = 'analysis', root
const json = (body, status = 200) => new Response(JSON.stringify(body), { status })
global.fetch = async (url, init = {}) => {
  requests.push({ url, init })
  assert.equal(init.credentials, 'same-origin')
  if (url === '/api/terms/current') return json([{ id: 1, type: 'SERVICE', required: true, version: 'v1', effective_at: '2026-09-01' }])
  if (url.startsWith('/api/me/analyses?')) return json({ items: [], limit: 20, offset: 0, has_more: false })
  if (url === '/api/me' && init.method === 'DELETE') {
    if (pendingDelete) await new Promise(resolve => { releaseDelete = resolve })
    return deleteFails ? json({ detail: '탈퇴 처리에 실패했습니다' }, 503) : new Response(null, { status: 204 })
  }
  if (url === '/api/me') return json({ email: 'member@example.com', nationality: 'KR', resides_in_korea: true, google_linked: false })
  if (url === '/api/me/consents' && init.method === 'POST') {
    const body = JSON.parse(init.body)
    assert.notEqual(body.type, 'SERVICE')
    if (changeFails) return json({ detail: '동의 저장에 실패했습니다' }, 503)
    const item = consents.find(item => item.type === body.type)
    item.agreed = body.action === 'AGREE'; item.version = 'v1'
    return json(item)
  }
  if (url === '/api/me/consents') return loadFails ? json({ detail: '동의 조회에 실패했습니다' }, 503) : json(consents)
  throw new Error('Unexpected API ' + url)
}
function Harness() {
  const [actor, setActor] = React.useState({ kind: 'member' })
  return React.createElement(AccountPage, {
    actor, onActorChange: async () => { actorChanges++; setActor({ kind: 'anonymous' }) },
    onLogout: () => { logoutCalls++; result = null }, onLogin() {}, onSignup() {}, onSession() {}, onStart() {},
  })
}
const button = text => [...document.querySelectorAll('button')].find(item => item.textContent.trim() === text)
const checkbox = text => [...document.querySelectorAll('label')].find(item => item.textContent.includes(text))?.querySelector('input[type=checkbox]')
async function click(text) { const item = button(text); assert(item && !item.disabled, text); await act(async () => item.click()) }
async function check(text) { const item = checkbox(text); assert(item && !item.disabled, text); await act(async () => item.click()) }
async function navigate(hash) { await act(async () => { window.history.replaceState(null, '', hash); window.dispatchEvent(new dom.window.HashChangeEvent('hashchange')) }) }
async function mount() {
  if (root) await act(async () => root.unmount())
  consents = structuredClone(initialConsents); requests = []; logoutCalls = 0; actorChanges = 0; result = 'analysis'
  window.history.replaceState(null, '', '#/start')
  root = createRoot(document.getElementById('root'))
  await act(async () => root.render(React.createElement(Harness)))
}
;(async () => {
  await mount()
  assert(document.querySelector('.account-history'))
  assert(document.querySelector('.account-profile-top .account-email').textContent.includes('member@example.com'))
  assert(!document.querySelector('.account-language'))
  assert(!document.querySelector('.account-preferences'))
  assert(!requests.some(r => r.url === '/api/me/consents'))
  assert.equal(document.querySelector('.account-settings-link').getAttribute('href'), '#/start?view=settings')
  await navigate('#/start?view=settings')
  assert(!document.querySelector('.account-history'))
  assert(!document.querySelector('.account-profile'))
  assert(document.body.textContent.includes('계정 설정'))
  await navigate('#/start')
  assert(document.querySelector('.account-history'))
  await navigate('#/start?view=settings')
  assert(checkbox('서비스 이용').disabled)
  assert(checkbox('서비스 이용').checked)
  assert(!checkbox('사진 보관').checked)
  assert(checkbox('마케팅 수신').checked)
  await check('사진 보관')
  assert(checkbox('사진 보관').checked)
  assert.deepEqual(JSON.parse(requests.filter(r => r.init.method === 'POST').at(-1).init.body), { type: 'PHOTO_STORAGE', action: 'AGREE' })
  await check('사진 보관')
  assert(!checkbox('사진 보관').checked)
  assert.equal(JSON.parse(requests.filter(r => r.init.method === 'POST').at(-1).init.body).action, 'WITHDRAW')
  changeFails = true
  await check('마케팅 수신')
  assert(checkbox('마케팅 수신').checked)
  assert(document.body.textContent.includes('동의 저장에 실패했습니다'))
  changeFails = false

  await click('회원 탈퇴')
  assert(button('확인하고 탈퇴하기').disabled)
  assert.equal(requests.filter(r => r.init.method === 'DELETE').length, 0)
  await check('삭제 내용을 확인')
  await click('탈퇴 취소')
  assert.equal(requests.filter(r => r.init.method === 'DELETE').length, 0)
  await click('회원 탈퇴')
  assert(!checkbox('삭제 내용을 확인').checked)
  await check('삭제 내용을 확인')
  deleteFails = true
  await click('확인하고 탈퇴하기')
  assert(document.body.textContent.includes('탈퇴 처리에 실패했습니다'))
  assert(document.querySelector('.account-settings'))
  assert.equal(logoutCalls, 0); assert.equal(actorChanges, 0); assert.equal(result, 'analysis')

  deleteFails = false; pendingDelete = true
  await click('확인하고 탈퇴하기')
  assert(button('확인하고 탈퇴하기').disabled)
  assert.equal(document.querySelector('.account-back').getAttribute('aria-disabled'), 'true')
  const count = requests.filter(r => r.init.method === 'DELETE').length
  await act(async () => button('확인하고 탈퇴하기').click())
  assert.equal(requests.filter(r => r.init.method === 'DELETE').length, count)
  await act(async () => releaseDelete())
  pendingDelete = false
  assert.equal(logoutCalls, 1); assert.equal(actorChanges, 1); assert.equal(result, null)
  assert(!document.body.textContent.includes('member@example.com'))
  assert(!document.querySelector('.account-preferences'))
  assert(!document.querySelector('.account-history'))
  assert(document.body.textContent.includes('회원 탈퇴가 완료되었습니다.'))

  loadFails = true
  await mount()
  await navigate('#/start?view=settings')
  assert(document.body.textContent.includes('동의 조회에 실패했습니다'))
  assert(!checkbox('사진 보관'))
  loadFails = false
  await click('동의 정보 다시 조회')
  assert(checkbox('마케팅 수신').checked)
  console.log('Account UI: compact profile, separate settings navigation/back, consent and withdrawal regression passed')
})().catch(err => { console.error(err); process.exitCode = 1 }).finally(async () => {
  if (root) await act(async () => root.unmount())
  dom.window.close(); fs.rmSync(dir, { recursive: true, force: true })
  // React 스케줄러의 MessagePort가 남아 있어도 완료된 테스트 프로세스는 종료한다.
  process.exit(process.exitCode || 0)
})
