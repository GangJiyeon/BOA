const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), assert = require('node:assert/strict')
const modules = process.env.BOA_TEST_MODULES
if (!modules) throw new Error('Set BOA_TEST_MODULES to a node_modules folder containing esbuild and jsdom')
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'boa-history-dom-')), frontend = path.resolve(__dirname, '..')
const appModules = path.join(frontend, 'node_modules')
fs.writeFileSync(path.join(dir, 'entry.tsx'), `export {default as React,act} from 'react';export {createRoot} from 'react-dom/client';export {default as AccountHistory} from ${JSON.stringify(path.join(frontend, 'src/components/AccountHistory'))};`)
require(path.join(modules, 'esbuild')).buildSync({ entryPoints: [path.join(dir, 'entry.tsx')], outfile: path.join(dir, 'bundle.cjs'), bundle: true,
  platform: 'browser', format: 'cjs', jsx: 'automatic', nodePaths: [appModules],
  define: { 'process.env.NODE_ENV': '"development"' }, alias: { react: path.join(appModules, 'react'), 'react-dom': path.join(appModules, 'react-dom') } })
const { JSDOM } = require(path.join(modules, 'jsdom')), dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' })
global.window = dom.window; global.document = dom.window.document; global.IS_REACT_ACT_ENVIRONMENT = true
const { React, act, createRoot, AccountHistory } = require(path.join(dir, 'bundle.cjs'))
const rows = [ { kind: 'skin', id: 12, created_at: '2026-11-14T01:00:00Z' }, { kind: 'hair', id: 12, created_at: '2026-11-13T01:00:00Z' } ]
const json = (body, status = 200) => new Response(JSON.stringify(body), { status })
let root, requests = [], listFails = false, detailFails = false, empty = false, deferDetail = false, releaseDetail, detailSignal
let deferList = false, releaseList, listSignal
const skin = { id: 12, logic_version: 'v1', moisture_source: 'none', scores: [] }
global.fetch = async (url, init = {}) => {
  requests.push({ url, init }); assert.equal(init.credentials, 'same-origin')
  if (url.startsWith('/api/me/analyses?')) {
    if (deferList) { listSignal = init.signal; return new Promise(resolve => { releaseList = resolve }) }
    if (listFails) return json({ detail: '이력 조회 실패' }, 503)
    const params = new URL(url, 'http://localhost').searchParams, kind = params.get('kind'), offset = Number(params.get('offset'))
    const items = empty ? [] : offset ? [{ kind: 'skin', id: 8, created_at: '2026-11-01T00:00:00Z' }] : rows.filter(item => kind === 'all' || item.kind === kind)
    return json({ items, limit: 20, offset, has_more: !empty && !offset && kind === 'all' })
  }
  if (url === '/api/skin/analyses/12') {
    if (deferDetail) { detailSignal = init.signal; return new Promise(resolve => { releaseDetail = resolve }) }
    return detailFails ? json({ detail: '결과가 삭제되었거나 조회할 수 없습니다' }, 404) : json(skin)
  }
  if (url === '/api/hair/recommend/12') return json({ run_id: 12, face_analysis_id: 1, created_at: rows[1].created_at, recommendations: [] })
  throw new Error('Unexpected API ' + url)
}
const button = text => [...document.querySelectorAll('button')].find(item => item.textContent.trim() === text)
async function click(text) { const item = button(text); assert(item && !item.disabled, text); await act(async () => item.click()) }
async function open(label) { const item = document.querySelector(`button[aria-label="${label}"]`); assert(item && !item.disabled, label); await act(async () => item.click()) }
async function filter(value) { await act(async () => { const select = document.querySelector('select'); select.value = value; select.dispatchEvent(new dom.window.Event('change', { bubbles: true })) }) }
async function mount() { if (root) await act(async () => root.unmount()); root = createRoot(document.getElementById('root')); await act(async () => root.render(React.createElement(AccountHistory))) }
;(async () => {
  await mount()
  assert.equal(document.querySelectorAll('.account-history-list li').length, 2)
  assert(button('이전 기록').disabled); assert(!button('다음 기록').disabled)
  assert(document.querySelector('time').textContent.includes('10:00')) // UTC+9
  await open('피부 분석 12번 결과 보기')
  assert(document.querySelector('.account-history-detail').textContent.includes('피부 분석 #12'))
  await open('헤어 추천 12번 결과 보기')
  assert(document.querySelector('.account-history-detail').textContent.includes('헤어 추천 #12'))
  assert(!document.querySelector('.account-history-detail').textContent.includes('피부 분석 #12'))
  await click('결과 닫기'); assert(!document.querySelector('.account-history-detail'))

  await click('다음 기록')
  assert(document.body.textContent.includes('2페이지')); assert(button('다음 기록').disabled)
  assert(requests.some(r => r.url.includes('offset=20')))
  await filter('hair')
  assert(document.body.textContent.includes('1페이지'))
  assert.equal(document.querySelectorAll('.account-history-list li').length, 1)
  assert(requests.at(-1).url.includes('kind=hair&limit=20&offset=0'))
  await filter('skin')
  detailFails = true; await open('피부 분석 12번 결과 보기')
  assert(document.body.textContent.includes('결과가 삭제되었거나 조회할 수 없습니다'))
  detailFails = false; await click('결과 다시 조회')
  assert(document.querySelector('.account-history-detail h3').textContent.includes('#12'))

  deferDetail = true; await open('피부 분석 12번 결과 보기')
  await filter('hair')
  assert(detailSignal.aborted)
  await act(async () => releaseDetail(json(skin)))
  assert(!document.querySelector('.account-history-detail'))
  deferDetail = false

  listFails = true; await click('이력 새로고침')
  assert(document.body.textContent.includes('이력 조회 실패'))
  listFails = false; await click('이력 다시 조회')
  assert(document.querySelector('.account-history-list'))
  empty = true; await click('이력 새로고침')
  assert(document.body.textContent.includes('아직 저장된 분석 이력이 없습니다'))
  empty = false; await mount()
  assert.equal(document.querySelectorAll('.account-history-list li').length, 2)
  assert(requests.filter(r => r.url.includes('/me/analyses?kind=all')).length >= 2)

  deferList = true; await click('이력 새로고침')
  assert(document.body.textContent.includes('분석 이력을 불러오는 중'))
  await act(async () => root.unmount()); root = null
  assert(listSignal.aborted)
  await act(async () => releaseList(json({ items: rows, limit: 20, offset: 0, has_more: false })))
  assert(!document.querySelector('.account-history'))
  console.log('Account history UI: list/filter/paging/KST/detail/retry/empty/remount and stale response/unmount cancellation passed')
})().catch(err => { console.error(err); process.exitCode = 1 }).finally(async () => {
  if (root) await act(async () => root.unmount())
  dom.window.close(); fs.rmSync(dir, { recursive: true, force: true }); process.exit(process.exitCode || 0)
})
