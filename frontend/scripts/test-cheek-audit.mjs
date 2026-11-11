import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import ts from 'typescript'
const source=await fs.readFile(new URL('../src/moisture/cheekAudit.ts',import.meta.url),'utf8')
const {outputText}=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}})
const {CheekAudit}=await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
const a=new CheekAudit(100,3), m={status:'sensor_error',reference:{amplitudeWarning:true}},v={phase:'release'}
a.event('connected',100);a.sample(m,v,200);m.status='valid';a.event('completed',300,{measurement_id:'x'});a.event('disconnected',400)
const out=a.export();assert.equal(out.site,'skin');assert.equal(out.hydration_model,null);assert.equal(out.dropped_entries,1);assert.equal(out.entries.length,3)
assert.equal(out.entries[0].measurement.status,'sensor_error');assert.equal(out.entries[0].elapsed_ms,100)
out.entries.length=0;assert.equal(a.export().entries.length,3)
console.log('Cheek audit: warning preservation, timestamps, completion/disconnect, copy isolation and bounded memory passed')
