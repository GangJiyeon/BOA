const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict')
const modules=process.env.BOA_TEST_MODULES
if(!modules)throw new Error('Set BOA_TEST_MODULES to frontend/node_modules')
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'boa-camera-dom-')),src=path.resolve(__dirname,'../src')
fs.writeFileSync(path.join(dir,'entry.tsx'),`export {default as React,act} from 'react';export {createRoot} from 'react-dom/client';export {default as HairPage} from ${JSON.stringify(src+'/pages/HairPage')};export {default as StudioPage} from ${JSON.stringify(src+'/pages/StudioPage')};`)
require(path.join(modules,'esbuild')).buildSync({entryPoints:[path.join(dir,'entry.tsx')],outfile:path.join(dir,'bundle.cjs'),bundle:true,platform:'browser',format:'cjs',jsx:'automatic',loader:{'.css':'empty'},define:{'import.meta.env.DEV':'false','process.env.NODE_ENV':'"development"'},alias:{react:path.join(modules,'react'),'react-dom':path.join(modules,'react-dom')}})
const {JSDOM}=require(path.join(modules,'jsdom')),dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'})
global.window=dom.window;global.document=dom.window.document;Object.defineProperty(global,'navigator',{value:dom.window.navigator,configurable:true});global.IS_REACT_ACT_ENVIRONMENT=true
const {React,act,createRoot,HairPage,StudioPage}=require(path.join(dir,'bundle.cjs'))
const requests=[],streams=[],captured=[];let deny=false,defer=false,resolveMedia,shot=0
function stream(){const state={stops:0};streams.push(state);return {getTracks:()=>[{stop(){state.stops++}}]}}
Object.defineProperty(navigator,'mediaDevices',{value:{getUserMedia:async constraints=>{
 assert.equal(constraints.audio,false)
 if(deny)throw Object.assign(new Error('denied'),{name:'NotAllowedError'})
 if(defer)return new Promise(resolve=>{resolveMedia=resolve})
 return stream()
}},configurable:true})
dom.window.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','')}
dom.window.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open')}
dom.window.HTMLMediaElement.prototype.play=async()=>{}
Object.defineProperty(dom.window.HTMLVideoElement.prototype,'videoWidth',{get:()=>1280})
Object.defineProperty(dom.window.HTMLVideoElement.prototype,'videoHeight',{get:()=>960})
dom.window.HTMLCanvasElement.prototype.getContext=()=>({translate(){},scale(){},drawImage(){}})
dom.window.HTMLCanvasElement.prototype.toBlob=function(callback,type){assert.equal(type,'image/jpeg');captured.push(++shot);callback(new Blob([`shot:${shot}`],{type}))}
const catalog=[{style_id:'bob',name:'칼단발',sex:'female',length:'short',texture:'straight',image:null}]
const rec={run_id:9,recommendations:[{style_id:'bob',name:'칼단발',rank:1,score:.9,image:null}]}
const json=(value,status=200)=>new Response(JSON.stringify(value),{status})
global.fetch=async(url,init={})=>{
 requests.push({url,init})
 if(url==='/api/hair/styles')return json(catalog)
 if(url==='/api/hair/face-analysis/photos')return json({id:5,face_shape:'oval'})
 if(url==='/api/hair/recommend')return json(rec)
 if(url==='/api/studio/hair-renders')return json({id:18,style_id:'bob',status:'pending',error:null,light:null,mid:null},202)
 throw new Error('Unexpected API '+url)
}
const click=async text=>{const button=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===text);assert(button&&!button.disabled,text);await act(async()=>button.click())}
const clickLabel=async label=>{const button=document.querySelector(`button[aria-label="${label}"]`);assert(button&&!button.disabled,label);await act(async()=>button.click())}
async function take(text='사진 찍기'){
 await click(text)
 assert(document.querySelector('dialog[open]'))
 await act(async()=>document.querySelector('video').dispatchEvent(new dom.window.Event('loadeddata')))
 await click('촬영하기')
 assert(!document.querySelector('dialog'));assert(streams.at(-1).stops>=1)
}
;(async()=>{
 let root=createRoot(document.getElementById('root'));const results=[]
 await act(async()=>root.render(React.createElement(HairPage,{onResult:value=>results.push(value)})))
 await take();assert.equal(document.querySelectorAll('.photo-preview').length,1)
 assert.equal(requests.filter(r=>r.url.includes('face-analysis')).length,0,'capture alone does not upload')
 await click('얼굴 분석하고 헤어 추천받기')
 let face=requests.filter(r=>r.url.includes('face-analysis')).at(-1)
 assert.equal(face.init.body.getAll('photos').length,1);assert.equal(face.init.body.get('photos').type,'image/jpeg')
 assert.equal(await results.at(-1).photo.text(),'shot:1')
 await take('다음 사진 찍기');assert.equal(document.querySelectorAll('.photo-preview').length,2)
 assert(document.querySelector('.recommend-button').disabled)
 await take('다음 사진 찍기');assert.equal(document.querySelectorAll('.photo-preview').length,3)
 const full=[...document.querySelectorAll('button')].find(b=>b.textContent==='3장 촬영 완료');assert(full.disabled)
 await clickLabel('1번째 사진 다시 촬영')
 await act(async()=>document.querySelector('video').dispatchEvent(new dom.window.Event('loadeddata')))
 await click('촬영하기');assert.equal(document.querySelectorAll('.photo-preview').length,3)
 await click('얼굴 분석하고 헤어 추천받기')
 face=requests.filter(r=>r.url.includes('face-analysis')).at(-1)
 assert.deepEqual(await Promise.all(face.init.body.getAll('photos').map(file=>file.text())),['shot:4','shot:2','shot:3'])
 assert.equal(await results.at(-1).photo.text(),'shot:4','retaken front photo is passed on to Studio')
 await act(async()=>root.unmount())
 root=createRoot(document.getElementById('root'))
 await act(async()=>root.render(React.createElement(StudioPage,{hair:null,onUsed:()=>{}})))
 await take();await act(async()=>document.querySelector('input[value="bob"]').click())
 await click('AI로 헤어 합성하기')
 const post=requests.find(r=>r.url==='/api/studio/hair-renders')
 assert.equal(await post.init.body.get('photo').text(),'shot:5');assert(!post.init.body.has('run_id'))
 await act(async()=>root.unmount()) // abort pending polling before any second request
 root=createRoot(document.getElementById('root'))
 await act(async()=>root.render(React.createElement(StudioPage,{hair:null,onUsed:()=>{}})))
 deny=true;await click('사진 찍기');assert(document.querySelector('dialog [role=alert]').textContent.includes('권한'))
 await clickLabel('카메라 닫기');assert(document.querySelector('input[type=file]'));assert(!document.querySelector('input[type=file]').disabled)
 deny=false;defer=true;await click('사진 찍기');await click('취소')
 const late=stream();await act(async()=>resolveMedia(late));assert(streams.at(-1).stops>=1);assert.equal(document.querySelectorAll('.photo-preview').length,0)
 defer=false;await click('사진 찍기');await act(async()=>window.dispatchEvent(new dom.window.HashChangeEvent('hashchange')))
 assert(!document.querySelector('dialog'));assert(streams.at(-1).stops>=1)
 await act(async()=>root.unmount());dom.window.close();fs.rmSync(dir,{recursive:true,force:true})
 console.log('Camera DOM: hair 1/3-shot input, ordered retake, front photo handoff, Studio JPEG upload, permission fallback, late permission cleanup and navigation shutdown passed (camera mocked)');process.exit(0)
})().catch(error=>{console.error(error);dom.window.close();process.exit(1)})
