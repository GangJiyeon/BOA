import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import ts from 'typescript'
let source=await fs.readFile(new URL('../src/moisture/autoMeasurement.ts',import.meta.url),'utf8')
const estimateSource=await fs.readFile(new URL('../src/moisture/hydrationEstimate.ts',import.meta.url),'utf8')
const estimateJs=ts.transpileModule(estimateSource,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText
const estimateUrl=`data:text/javascript;base64,${Buffer.from(estimateJs).toString('base64')}`
source=source.replace("'./hydrationEstimate'",JSON.stringify(estimateUrl))
const protocolSource=await fs.readFile(new URL('../src/moisture/protocol.ts',import.meta.url),'utf8')
const protocolJs=ts.transpileModule(protocolSource,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText
source=source.replaceAll("'./protocol'",JSON.stringify(`data:text/javascript;base64,${Buffer.from(protocolJs).toString('base64')}`))
const {estimateHydration}=await import(estimateUrl)
const profile={reference_divider:44,output_gain:16,offset:170,sensor_divider:2,verified:true}
const {outputText}=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}})
const {AutoMeasurement,summarize,normalizedMoistureScore,NORMALIZATION_VERSION}=await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
function rig({baseline=2540,seq=0,uptime=0}={}){
 let host=0,id=0;const results=[],machine=new AutoMeasurement(()=>`result-${++id}`)
 function push(count=baseline,{dt=100,hostDt=dt,...extra}={}){
  host+=hostDt;seq=(seq+1)&65535;uptime=(uptime+dt)>>>0
  const m={protocol_version:4,sensor_profile:profile,source:'ble_sensor',status:'valid',raw_value:count,unit:'fdc2112_count',sequence:seq,device_uptime_ms:uptime,received_at:'2026-01-01T00:00:00Z',reference:{calibration:'ready',baseline,average:count,percent:Math.floor(Math.max(0,baseline-count)*100/baseline),amplitudeWarning:false},...extra}
  const done=machine.push(m,host);if(done)results.push(done);return m
 }
 const many=(n,c)=>{for(let i=0;i<n;i++)push(c)}
 function tick(now){host=now;machine.tick(host);const done=machine.takeCompleted();if(done)results.push(done)}
 return{machine,results,push,many,tick,get host(){return host}}
}
let r=rig();r.many(25,2540);assert.equal(r.machine.view().phase,'waiting')
r.push(2500);const start=r.host;r.many(29,2500)
assert.equal(r.results.length,0);r.tick(start+2999);assert.equal(r.results.length,0)
r.tick(start+3000);assert.equal(r.results.length,1);assert.equal(summarize(r.results[0]).duration_ms,3000)
assert.equal(r.results[0].normalization_version,NORMALIZATION_VERSION)
assert.equal(r.results[0].window_end_uptime_ms,(r.results[0].samples[0].uptime_ms+3000)>>>0)
assert.equal(r.results[0].samples.length,30)
r.many(100,2500);r.many(40,2540);r.many(80,2500);assert.equal(r.results.length,1,'no automatic repeat')
r.machine.reset();r.many(25,2540);r.push(2500);const next=r.host;r.many(29,2500);r.tick(next+3000);assert.equal(r.results.length,2)
// Continuous drift is analyzed within 3 seconds; it cannot extend the window.
r=rig();r.many(25,2540);r.push(2520);const rampStart=r.host
for(let i=1;i<30;i++)r.push(2520-i)
r.tick(rampStart+3000);assert.equal(r.results.length,1);assert.equal(r.machine.view().phase,'completed')
assert(summarize(r.results[0]).normalized_score>=1)
// BLE packets can close the window; a packet beyond its endpoint is excluded.
r=rig();r.many(25,2540);r.push(2500);r.many(30,2500);assert.equal(r.results.length,1)
assert(r.results[0].samples.every(s=>((s.uptime_ms-r.results[0].samples[0].uptime_ms)>>>0)<=3000))
// Physical faults remain faults; we do not fabricate a result for missing data.
r=rig();r.many(25,2540);r.push(2500);const sparseStart=r.host
r.push(100,{status:'sensor_error',raw_value:null,reference:{calibration:'ready',baseline:2540,average:100,percent:null,amplitudeWarning:true,warning_flags:0x1000}})
r.many(28,2500);r.tick(sparseStart+3000);assert.equal(r.results.length,1)
assert.equal(r.results[0].samples.length,29);assert.equal(r.results[0].discarded_samples[0].diagnostic_count,100)
assert.equal(summarize(r.results[0]).terminal_count,2500,'warning value must not enter representative sample')
r=rig();r.many(25,2540);r.push(2500);const waitingStart=r.host
r.push(2500,{status:'not_ready',raw_value:null});r.many(28,2500);r.tick(waitingStart+3000);assert.equal(r.results.length,1)
r=rig();r.many(25,2540);r.push(2500);for(let i=0;i<3;i++)r.push(2500,{status:'sensor_error',raw_value:null});r.many(60,2500);assert.equal(r.results.length,0)
r=rig();r.many(25,2540);r.push(2500);r.many(29,2540);r.tick(r.host+100);assert.equal(r.results.length,0);assert.equal(r.machine.view().phase,'rejected')
r=rig();r.many(25,2540);r.push(2500);r.many(29,2500);r.tick(r.host+1000);assert.equal(r.results.length,0)
r=rig();r.many(25,2540);r.push(2500);for(let i=0;i<32;i++)r.push(2500,{hostDt:1});assert.equal(r.results.length,0,'buffered old data cannot complete early')
r=rig({seq:65510,uptime:0xfffff000});r.many(25,2540);r.push(2500);r.many(30,2500);assert.equal(r.results.length,1,'counter wrap')
// Normalization is monotone and bounded; it preserves the physical ratio.
assert.equal(normalizedMoistureScore(2540,2540),1)
assert.equal(normalizedMoistureScore(2540,2000),100)
let previous=1;for(let c=2540;c>=2000;c--){const n=normalizedMoistureScore(2540,c);assert(n>=previous&&n<=100);previous=n}
assert.equal(normalizedMoistureScore(508,504),normalizedMoistureScore(2542,2526))
// Replay the latest actual capture. Record the first 3 seconds only.
const trace=JSON.parse(await fs.readFile(new URL('../../fixtures/skin-audit-fine.json',import.meta.url),'utf8'))
const replay=new AutoMeasurement(()=>'00000000-0000-4000-8000-000000000007');const actual=[];let contactHost=null,finishHost=null
for(const e of trace.entries){const done=replay.push({...e.measurement,protocol_version:4,sensor_profile:profile},e.elapsed_ms);if(contactHost===null&&replay.view().phase==='collecting')contactHost=e.elapsed_ms;if(done){actual.push(done);finishHost=e.elapsed_ms}}
assert.equal(actual.length,1);assert(finishHost-contactHost>=3000&&finishHost-contactHost<3150)
assert.equal(summarize(actual[0]).duration_ms,3000);assert.equal(actual[0].algorithm_version,'skin-fixed-3s-v1')
assert.equal(replay.view().phase,'completed')
console.log('Fixed 3s: timer and packet completion, continuous drift, no extension/repeat, faults, dropout, buffered packets, counter wraps, normalization passed')
console.log('Actual trace fixed window:',JSON.stringify({score:summarize(actual[0]).normalized_score,samples:actual[0].samples.length,first:actual[0].samples[0],last:actual[0].samples.at(-1),terminal:summarize(actual[0]).terminal_count,host_duration_ms:finishHost-contactHost}))
assert.equal(summarize(actual[0]).normalized_score,3,'new 0..60 scale; replay profile is assumed, not measured ground truth')
assert.equal(summarize(actual[0]).estimated_state,'low')
// Configuration is supplied ONLY for software replay; it was not in the old trace.
for(const [response,state] of [[22.99,'low'],[23,'normal'],[45.99,'normal'],[46,'sufficient']]){
 const b=2510,c=(500*(1-response/100)+170)*44/11-170
 assert.equal(estimateHydration(b,c,44).estimated_state,state)
}
r=rig();r.many(25,2540);r.push(2500);r.push(2500,{sensor_profile:{...profile,reference_divider:22}});r.many(30,2500);assert.equal(r.results.length,0);assert.equal(r.machine.view().phase,'rejected')
r=rig();r.many(30,2540);r.push(2500,{protocol_version:3,sensor_profile:undefined});assert.equal(r.machine.view().phase,'needs_calibration')
console.log('Experimental estimator: research-prior boundaries, old-firmware gate and mid-contact profile change passed')

// A warning in the representative final second must not bias the result low.
r=rig();r.many(25,2540);r.push(2500);const terminalFaultStart=r.host;r.many(21,2500);r.push(2500,{status:'sensor_error',raw_value:null});r.many(7,2500);r.tick(terminalFaultStart+3000);assert.equal(r.results.length,0);assert.equal(r.machine.view().phase,'rejected')
console.log('Terminal-error censoring protection passed')

// Compare the actual two contact representative values on the new display.
for(const [count,score] of [[2506,3],[2502,3]]){
 const v2=estimateHydration(2538,count,44),v1=estimateHydration(2538,count,44,'hydration-estimate-pnj-2023-v1')
 assert.equal(v2.normalized_score,score);assert.equal(v1.normalized_score,3)
 assert.equal(v1.estimated_state,v2.estimated_state);assert.equal(v1.manufacturer_response,v2.manufacturer_response)
}
console.log('Actual before/after wash replay: 3/60 each; same experimental state; historical scales tested separately')
