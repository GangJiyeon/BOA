import fs from 'node:fs/promises'
import assert from 'node:assert/strict'
import ts from 'typescript'
const source=await fs.readFile(new URL('../src/moisture/hydrationEstimate.ts',import.meta.url),'utf8')
const {outputText}=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}})
const m=await import('data:text/javascript;base64,'+Buffer.from(outputText).toString('base64'))
assert.equal(m.estimateHydration(2540,2513,44,m.DISPLAY_VERSION).normalized_score,3)
for(const [v,g] of Object.entries(m.PROVISIONAL_GAINS)){
 const r=m.estimateHydration(2540,2513,44,v)
 assert.equal(r.normalized_score,({5:7,10:11,20:28})[g])
 assert(r.moisture_level_label.startsWith('임시 보정'))
 const seen=new Set();let prev=-1
 for(let i=0;i<=100000;i++) {const s=m.scoreFromResponse(i/1000,v);assert(s>=prev&&s<=60);seen.add(s);prev=s}
 assert.equal(seen.size,61)
}
assert.equal(m.ACTIVE_VERSION,'boa-moisture-60-provisional-gain10-v1')
console.log('Provisional 5/10/20 gains, original version, sample replay, monotonicity and all 61 scores passed')
