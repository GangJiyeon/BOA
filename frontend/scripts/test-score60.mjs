import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import ts from 'typescript'
const src=await fs.readFile(new URL('../src/moisture/hydrationEstimate.ts',import.meta.url),'utf8')
const js=ts.transpileModule(src,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText
const url=`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`
const {scoreFromResponse,classification60,estimateHydration,DISPLAY_VERSION,LEGACY_DISPLAY_VERSION,scoreMaximum}=await import(url)
const fixtures=JSON.parse(await fs.readFile(new URL('../../fixtures/moisture-score60-parity.json',import.meta.url),'utf8'))
for(const [response,score,level] of fixtures.responses){
  assert.equal(scoreFromResponse(response),score,`Python/JS score at ${response}`)
  assert.equal(classification60(score).moisture_level,level)
}
const found=new Set()
for(let n=0;n<=100000;n++)found.add(scoreFromResponse(n/1000))
assert.deepEqual([...found],[...Array(61).keys()])
for(const row of fixtures.measurements){
  const actual=estimateHydration(row.baseline,row.count,row.divider,DISPLAY_VERSION)
  assert.equal(actual.normalized_score,row.score)
  assert.equal(actual.moisture_level,row.level)
  assert.equal(actual.estimated_state,row.state)
  assert.equal(scoreMaximum(actual),60)
}
for(const invalid of [-1,100.1,NaN,Infinity])assert.throws(()=>scoreFromResponse(invalid))
for(const invalid of [-1,61,.1])assert.throws(()=>classification60(invalid))
assert.equal(estimateHydration(2538,2506,44,LEGACY_DISPLAY_VERSION).normalized_score,24)
// Exercise the actual UI render for every integer score, including a valid zero.
import React from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
let cards=await fs.readFile(new URL('../src/components/MetricScores.tsx',import.meta.url),'utf8')
cards=cards.replace("'../moisture/hydrationEstimate'",JSON.stringify(url))
const reactUrl=new URL('../node_modules/react/index.js',import.meta.url).href
cards=`import React from ${JSON.stringify(reactUrl)}\n`+cards
const cardJs=ts.transpileModule(cards,{compilerOptions:{jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText
const {default:MetricScores}=await import(`data:text/javascript;base64,${Buffer.from(cardJs).toString('base64')}`)
for(let score=0;score<=60;score++){
  const grade=classification60(score)
  const html=renderToStaticMarkup(React.createElement(MetricScores,{scores:[],moisture:{...grade,normalized_score:score,used_for_scoring:true,relative_percent:0,estimation_version:DISPLAY_VERSION}}))
  const category = score < 20 ? '개선 필요' : score < 50 ? '보통' : '양호'
  assert(html.includes(`<strong>${category}</strong>`))
  assert(!html.includes('/ 60') && !html.includes('/6단계'))
}
const renderMoisture = moisture => renderToStaticMarkup(React.createElement(MetricScores,{scores:[],moisture}))
assert(renderMoisture({score_category:'양호',estimated_state:'low',used_for_scoring:true}).includes('<strong>양호</strong>'))
assert(renderMoisture({score_category:'양호',resolution_limited:true}).includes('<strong>판정 불가</strong>'))
assert(renderMoisture({normalized_score:50,used_for_scoring:false}).includes('<strong>판정 불가</strong>'))
console.log(`score60: ${fixtures.responses.length} Python/JS fixtures, rendered categories for all 61 scores, and legacy or limited measurements passed`)
