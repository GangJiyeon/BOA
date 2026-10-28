// Isolated DOM test dependencies: set BOA_TEST_MODULES to their node_modules directory.
const path = require('node:path'), fs = require('node:fs'), os = require('node:os');
const modules = process.env.BOA_TEST_MODULES;
if (!modules) throw new Error('Set BOA_TEST_MODULES; see docs/moisture-v7.md');
const output = fs.mkdtempSync(path.join(os.tmpdir(),'boa-moisture-dom-'));
require(path.join(modules,'esbuild')).buildSync({entryPoints:[path.join(__dirname,'moisture-dom-entry.tsx')],outfile:path.join(output,'bundle.cjs'),bundle:true,platform:'browser',format:'cjs',jsx:'automatic',loader:{'.css':'empty'},define:{'import.meta.env.DEV':'true','process.env.NODE_ENV':'"development"'},alias:{react:path.join(modules,'react'),'react-dom':path.join(modules,'react-dom')}});
const {JSDOM}=require(path.join(modules,'jsdom'));const assert=require('node:assert/strict');
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});global.window=dom.window;global.document=dom.window.document;Object.defineProperty(global,'navigator',{value:dom.window.navigator,configurable:true});global.IS_REACT_ACT_ENVIRONMENT=true;
global.ResizeObserver=class {observe(){} disconnect(){}};
let host=0;Object.defineProperty(global,'performance',{value:{now:()=>host,measure(){},mark(){},clearMarks(){},clearMeasures(){}},configurable:true});
let seq=0;const completed=[];const warnings=[];const oldError=console.error;console.error=(...args)=>{warnings.push(args.join(' '));oldError(...args)};
class C extends dom.window.EventTarget {async startNotifications(){return this}async stopNotifications(){return this}async writeValueWithResponse(v){assert.deepEqual([...v],[1]);send(2540,1)}}
const measurement=new C(),command=new C(),device=new dom.window.EventTarget();
device.gatt={connected:false,connect:async()=>{device.gatt.connected=true;return {getPrimaryService:async()=>({getCharacteristic:async uuid=>uuid.startsWith('98b10003')?command:uuid.startsWith('98b10005')?measurement:await Promise.reject(new DOMException('legacy v4 firmware','NotFoundError'))})}},disconnect:()=>{device.gatt.connected=false}};
Object.defineProperty(navigator,'bluetooth',{value:{requestDevice:async()=>device}});Object.defineProperty(window,'isSecureContext',{value:true});
function send(count=2540,cal=2){host+=100;const v=new DataView(new ArrayBuffer(20));v.setUint8(0,4);v.setUint16(18,0x42c,true);v.setUint8(2,cal===1?2:0);v.setUint8(3,cal);v.setUint16(4,cal===1?65535:count,true);v.setUint16(6,seq++&65535,true);v.setUint32(8,host,true);v.setUint16(12,cal===2?2540:65535,true);v.setUint16(14,cal===1?65535:count,true);v.setUint16(16,cal===2?Math.floor(Math.max(0,2540-count)*100/2540):65535,true);measurement.value=v;measurement.dispatchEvent(new dom.window.Event('characteristicvaluechanged'))}
const {act,createRoot,React,MoisturePanel,AutoHarness,ResultHarness,CosmeticPreview}=require(path.join(output,'bundle.cjs'));const root=createRoot(document.getElementById('root'));const render=props=>act(async()=>root.render(React.createElement(MoisturePanel,{analysisId:10,onComplete:r=>completed.push(r),...props})));
const click=async name=>{const button=[...document.querySelectorAll('button')].find(e=>e.textContent.trim()===name);assert(button,name);assert(!button.disabled,name+' disabled');await act(async()=>button.click())};
(async()=>{
 await render();await click('측정기 연결');await act(async()=>send(2540,0));await click('기준값 보정')
 for(let i=0;i<25;i++)await act(async()=>send(2540))
 await act(async()=>send(2500));const captureStart=host
 for(let i=0;i<29;i++)await act(async()=>send(2500))
 assert.equal(completed.length,0,'no early result');assert(document.querySelector('progress[aria-label="3초 측정 진행률"]'))
 host=captureStart+3000;await act(async()=>await new Promise(resolve=>setTimeout(resolve,35)))
 assert.equal(completed.length,1,'timer closes at 3s without waiting for another packet')
 assert(document.body.textContent.includes('측정 완료 · 수분 3/60'))
 assert.equal(document.querySelector('.moisture-reading strong').textContent,'3/ 60')
 assert.equal(document.querySelectorAll('.moisture-panel details').length,1)
 assert(!document.querySelector('.moisture-reading').textContent.includes('%'))
 assert(!document.body.textContent.includes('신호 안정화 대기'))
 for(let i=0;i<50;i++)await act(async()=>send(2500))
 for(let i=0;i<30;i++)await act(async()=>send(2540))
 for(let i=0;i<50;i++)await act(async()=>send(2500))
 assert.equal(completed.length,1,'hold/release/recontact do not restart')
 await click('다시 측정');for(let i=0;i<25;i++)await act(async()=>send(2540));for(let i=0;i<31;i++)await act(async()=>send(2500))
 assert.equal(completed.length,2)
 await click('연결 해제');assert(document.body.textContent.includes('측정 완료 · 수분 3/60'))
 // Actual new sensor trace through the real BLE decoder, not a mocked summary.
 await act(async()=>root.render(null));await render({key:'actual-fixed'});await click('측정기 연결')
 const trace=JSON.parse(fs.readFileSync(path.join(__dirname,'../../fixtures/skin-audit-fine.json'),'utf8'))
 const offset=host+1000,before=completed.length
 for(const e of trace.entries){
  host=offset+e.elapsed_ms;const m=e.measurement,ref=m.reference,v=new DataView(new ArrayBuffer(20))
  v.setUint8(0,4);v.setUint16(18,0x42c,true);v.setUint8(3,2);v.setUint16(4,m.raw_value,true);v.setUint16(6,m.sequence,true);v.setUint32(8,m.device_uptime_ms,true)
  v.setUint16(12,ref.baseline,true);v.setUint16(14,m.raw_value,true);v.setUint16(16,Math.floor(Math.max(0,ref.baseline-m.raw_value)*100/ref.baseline),true)
  measurement.value=v;await act(async()=>measurement.dispatchEvent(new dom.window.Event('characteristicvaluechanged')))
 }
 assert.equal(completed.length,before+1);assert(document.body.textContent.includes('측정 완료 · 수분 3/60'))
 assert.equal(completed.at(-1).window_end_uptime_ms-completed.at(-1).samples[0].uptime_ms,3000)
 // No post-completion recording or repeated callback.
 await act(async()=>root.render(null));let unexpected=0
 const initial=completed.at(-1),done=()=>unexpected++
 let post={protocol_version:3,source:'ble_sensor',sequence:999,raw_value:2540,reference:{calibration:'ready'}}
 await act(async()=>root.render(React.createElement(AutoHarness,{value:post,initial,onComplete:done})))
 const beforeAudit=global.autoHook.exportAudit().entries.filter(e=>e.kind==='sample').length
 host+=100;post={...post,sequence:1000};await act(async()=>root.render(React.createElement(AutoHarness,{value:post,initial,onComplete:done})))
 assert.equal(global.autoHook.exportAudit().entries.filter(e=>e.kind==='sample').length,beforeAudit);assert.equal(unexpected,0)
 // Persistence stays bound to the same analysis and survives navigation.
 let requests=[];global.fetch=(url,init)=>new Promise((resolve,reject)=>requests.push({url,init,resolve,reject}))
 const show=props=>act(async()=>root.render(React.createElement(ResultHarness,{id:null,scope:1,active:true,...props})))
 await show({});await act(async()=>global.resultHook.complete(completed[0]));assert.equal(requests.length,0)
 await show({id:10});assert.equal(JSON.parse(requests[0].init.body).analysis_id,10)
 await show({id:11});assert(requests[0].init.signal.aborted);assert.equal(JSON.parse(requests[1].init.body).analysis_id,10)
 await act(async()=>requests[1].reject(new Error('offline')));await act(async()=>global.resultHook.retry());assert.equal(requests.length,3)
 await show({id:12,scope:2});assert(requests[2].init.signal.aborted)
 await act(async()=>requests[2].resolve(new Response(JSON.stringify({measurement_id:completed[0].measurement_id,analysis_id:10}))));assert.equal(global.resultHook.receipt,null)
 // Full photo UI: measured score -> first photo -> stored analysis -> recommendation.
 await act(async()=>root.unmount());const flowRoot=createRoot(document.getElementById('root')),analyses=[]
 const flow=active=>act(async()=>flowRoot.render(React.createElement(CosmeticPreview,{active,onAnalysis:v=>analyses.push(v)})))
 await flow(true);await click('측정기 연결');await act(async()=>send(2540,0));await click('기준값 보정')
 for(let i=0;i<25;i++)await act(async()=>send(2540));for(let i=0;i<31;i++)await act(async()=>send(2500))
 assert(document.body.textContent.includes('수분 3/60'))
 const selectPhoto=async name=>{const input=document.querySelector('input[type=file]');Object.defineProperty(input,'files',{value:[new File(['image'],name,{type:'image/jpeg'})],configurable:true});await act(async()=>input.dispatchEvent(new dom.window.Event('change',{bubbles:true})))}
 const dryness=[...document.querySelectorAll('input[type=checkbox]')].find(e=>e.parentElement.textContent.includes('수분 부족이면 향료'));assert(dryness);await act(async()=>dryness.click())
 await selectPhoto('first.jpg');requests=[]
 await act(async()=>document.querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})))
 const photoScores=['redness','brightness','trouble','uniformity'].map(metric_code=>({metric_code,metric_name:metric_code,score:50,category_name:'보통',higher_is_better:true}))
 await act(async()=>requests[0].resolve(new Response(JSON.stringify({id:77,logic_version:'photo_v1',moisture_source:'none',scores:photoScores}))))
 const save=requests.find(r=>r.url==='/api/skin/moisture/results');assert(save)
 const body=JSON.parse(save.init.body);assert.equal(body.analysis_id,77);assert.equal(body.result.algorithm_version,'skin-fixed-3s-v1')
 await flow(false);assert(!save.init.signal.aborted)
 await act(async()=>save.resolve(new Response(JSON.stringify({measurement_id:body.result.measurement_id,analysis_id:77,algorithm_version:'skin-fixed-3s-v1',relative_percent:1,baseline:2540,mean_count:2500,persisted:true,normalized_score:3,score_max:60,moisture_level:1,moisture_level_label:'매우 부족',estimated_state:'low',estimated_state_label:'부족',estimation_version:'boa-moisture-60-sqrt-v2',normalization_version:'boa-moisture-60-sqrt-v2',used_for_scoring:true,calibrated_score:null,score_category:'개선 필요',score_metric_name:'수분',scoring_status:'experimental_estimate',recommendation_eligible:false}))))
 assert.equal(analyses.at(-1).scores.find(s=>s.metric_code==='moisture').score,3)
 const recommendation=requests.find(r=>r.url!=='/api/skin/analyses/debug'&&r!==save);assert(recommendation)
 const preview={recommendation_mode:'targeted',recommendation_notice:'test',snapshot_token:'old',missing_metrics:[],recommendations:[],tie_groups:[],target_count:0,scorable_target_count:0,assessments:[],stats:{total_products:0,eligible_products:0},applied_exclusions:[],exclusion_details:[],notices:[],deferred_metrics:[]}
 await act(async()=>recommendation.resolve(new Response(JSON.stringify(preview))))
 const refreshed=requests.filter(r=>r.url===recommendation.url).at(-1);assert.notEqual(refreshed,recommendation)
 const payload=JSON.parse(refreshed.init.body);assert.equal(payload.scores.find(s=>s.metric_code==='moisture').score,3);assert.equal(payload.scores.length,5)
 assert.equal(payload.moisture_measurement_id,body.result.measurement_id,'recommendation uses the persisted sensor classification');assert.equal(payload.moisture_analysis_id,77)
 assert.equal(payload.avoid_dryness_triggers,true,'dryness option survives photo analysis and recommendation refresh')
 await act(async()=>refreshed.resolve(new Response(JSON.stringify({...preview,snapshot_token:'new'}))))
 await flow(true);await selectPhoto('replacement.jpg');assert(!document.body.textContent.includes('최근 측정 기록 · 수분'))
 await act(async()=>flowRoot.unmount());assert.deepEqual(warnings,[])
 console.log('DOM: fixed 3-second timer, assumed-profile trace 3/60, one completion, no post recording, compact UI, fixed analysis binding, photo + normalized recommendation path passed')
 dom.window.close();fs.rmSync(output,{recursive:true,force:true});process.exit(0)
})().catch(e=>{console.error(e);process.exit(1)});
