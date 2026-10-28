const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict')
const modules=process.env.BOA_TEST_MODULES
if(!modules)throw new Error('Set BOA_TEST_MODULES to frontend/node_modules')
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'boa-studio-dom-')),src=path.resolve(__dirname,'../src')
fs.writeFileSync(path.join(dir,'entry.tsx'),`export {default as React,act} from 'react';export {createRoot} from 'react-dom/client';export {default as HomePage} from ${JSON.stringify(src+'/pages/HomePage')};export {default as StudioPage} from ${JSON.stringify(src+'/pages/StudioPage')};`)
require(path.join(modules,'esbuild')).buildSync({entryPoints:[path.join(dir,'entry.tsx')],outfile:path.join(dir,'bundle.cjs'),bundle:true,platform:'browser',format:'cjs',jsx:'automatic',loader:{'.css':'empty'},define:{'import.meta.env.DEV':'false','process.env.NODE_ENV':'"development"'},alias:{react:path.join(modules,'react'),'react-dom':path.join(modules,'react-dom')}})
const {JSDOM}=require(path.join(modules,'jsdom')),dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/#/home'})
global.window=dom.window;global.document=dom.window.document;global.IS_REACT_ACT_ENVIRONMENT=true
window.scrollTo=()=>{};window.matchMedia=()=>({matches:false});dom.window.HTMLElement.prototype.scrollIntoView=()=>{}
// Deterministic pixels exercise the real color panel without external images.
global.createImageBitmap=async()=>({width:2,height:2,close(){}})
global.ImageData=class {constructor(width,height){this.width=width;this.height=height;this.data=new Uint8ClampedArray(width*height*4).fill(150)}}
dom.window.HTMLCanvasElement.prototype.getContext=()=>({drawImage(){},getImageData:()=>new ImageData(2,2),putImageData(){}})
const {React,act,createRoot,HomePage,StudioPage}=require(path.join(dir,'bundle.cjs'))
const requests=[],json=(body,status=200)=>new Response(JSON.stringify(body),{status})
let rendered=false,catalogState='ok'
const catalog=[{style_id:'bob',name:'칼단발',sex:'female',length:'short',texture:'straight',image:null},{style_id:'crew',name:'크루컷',sex:'male',length:'short',texture:'straight',image:null},{style_id:'wave',name:'웨이브',sex:'unisex',length:'long',texture:'wavy',image:null}]
global.fetch=async(url,init={})=>{
 requests.push({url,init})
 if(url.startsWith('/static/studio/'))return new Response(new Uint8Array([1,2,3]))
 if(url==='/api/hair/styles')return catalogState==='fail'?json({detail:'카탈로그 오프라인'},503):json(catalogState==='empty'?[]:catalog)
 if(url==='/api/health')return json({status:'ok',db:true,s3:false})
 if(url==='/api/actor')return json({kind:'guest'})
 if(url==='/api/guest/quota')return json(Object.fromEntries(['skin','hair','studio'].map(k=>[k,{limit:3,used:0,remaining:3}])))
 if(url==='/api/studio/hair-renders')return json({id:18,style_id:'bob',status:'pending',error:null,light:null,mid:null},202)
 if(url==='/api/studio/hair-renders/18'){
  rendered=true
  return json({id:18,style_id:'bob',status:'done',error:null,light:{image:'/static/studio/test/light.jpg',mask:'/static/studio/test/light_mask.png'},mid:{image:'/static/studio/test/mid.jpg',mask:'/static/studio/test/mid_mask.png'}})
 }
 throw new Error('Unexpected API request: '+url)
}
;(async()=>{
 let root=createRoot(document.getElementById('root'))
 await act(async()=>root.render(React.createElement(HomePage)))
 const tile=document.querySelector('.service-tile[href="#/studio"]')
 assert(tile);assert(!tile.textContent.includes('준비 중'));assert(tile.textContent.includes('스튜디오 열기'))
 await act(async()=>{window.location.hash='/studio';window.dispatchEvent(new dom.window.HashChangeEvent('hashchange'))})
 assert(document.body.textContent.includes('AI 헤어 스튜디오'))
 assert(document.body.textContent.includes('합성할 사진'));assert(document.querySelector('input[type=file]'))
 assert(!document.querySelector('.app-nav [href="#/studio"]').textContent.includes('준비 중'))
 const generate=()=>document.querySelector('.recommend-button')
 const choose=async name=>{
  const button=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===name)
  assert(button&&!button.disabled,name);await act(async()=>button.click())
 }
 const upload=async file=>{
  const input=document.querySelector('input[type=file]');assert(input)
  Object.defineProperty(input,'files',{value:[file],configurable:true})
  await act(async()=>input.dispatchEvent(new dom.window.Event('change',{bubbles:true})))
 }
 // No face analysis or recommendation is needed for the standalone path.
 assert(generate().disabled)
 const directPhoto=new File(['direct-photo'],'direct.jpg',{type:'image/jpeg'})
 await upload(directPhoto);assert(generate().disabled)
 await act(async()=>document.querySelector('input[value="bob"]').click())
 assert(!generate().disabled)
 await act(async()=>generate().click())
 let posts=requests.filter(r=>r.url==='/api/studio/hair-renders'),post=posts.at(-1)
 assert.equal(post.init.method,'POST');assert.equal(post.init.body.get('style_id'),'bob')
 assert.equal(post.init.body.get('photo').name,'direct.jpg');assert.equal(post.init.body.has('run_id'),false)
 assert(generate().disabled)
 await act(async()=>await new Promise(resolve=>setTimeout(resolve,2100)))
 assert(rendered);assert(document.body.textContent.includes('머리색 바꿔보기'))
 assert.equal(document.querySelectorAll('.swatch').length,40)
 const swatch=document.querySelector('.swatch');await act(async()=>swatch.click());assert(document.querySelector('canvas').getAttribute('aria-label').includes(swatch.title))
 const sex=document.querySelector('.studio-catalog-filters select')
 await act(async()=>{sex.value='male';sex.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert(!document.querySelector('input[value="bob"]'));assert(generate().disabled)
 assert(!document.body.textContent.includes('머리색 바꿔보기'))
 assert.equal(requests.filter(r=>r.url.includes('face-analysis')||r.url.includes('/hair/recommend')).length,0)
 await act(async()=>root.unmount())
 root=createRoot(document.getElementById('root'))
 const photo=new File(['test-photo'],'face.jpg',{type:'image/jpeg'}),hair={photo,analysis:{id:5,face_shape:'oval'},result:{run_id:9,recommendations:[{style_id:'bob',name:'칼단발',rank:1,score:.9,image:null}]}}
 let used=0
 await act(async()=>root.render(React.createElement(StudioPage,{hair,onUsed:()=>used++})))
 assert(!generate().disabled);assert(document.body.textContent.includes('face.jpg'))
 await act(async()=>generate().click())
 posts=requests.filter(r=>r.url==='/api/studio/hair-renders');post=posts.at(-1)
 assert.equal(post.init.body.get('style_id'),'bob');assert.equal(post.init.body.get('run_id'),'9');assert.equal(post.init.body.get('photo').name,'face.jpg');assert.equal(used,1)
 await act(async()=>await new Promise(resolve=>setTimeout(resolve,2100)))
 await choose('사진 업로드 · 직접 선택');assert(document.querySelector('input[type=file]'));assert(generate().disabled)
 await choose('헤어 추천에서 가져오기');assert(!generate().disabled)
 await act(async()=>root.unmount())
 // Catalog errors can be retried; an empty catalog cannot create a request.
 root=createRoot(document.getElementById('root'));catalogState='fail'
 await act(async()=>root.render(React.createElement(StudioPage,{hair:null,onUsed:()=>{}})))
 assert(document.querySelector('[role=alert]').textContent.includes('카탈로그 오프라인'));assert(generate().disabled)
 catalogState='ok';await choose('다시 조회');assert.equal(document.querySelectorAll('.studio-style').length,3)
 await act(async()=>root.unmount())
 root=createRoot(document.getElementById('root'));catalogState='empty'
 await act(async()=>root.render(React.createElement(StudioPage,{hair:null,onUsed:()=>{}})))
 assert(document.body.textContent.includes('등록된 헤어스타일이 없습니다.'));assert(generate().disabled)
 await act(async()=>root.unmount());dom.window.close();fs.rmSync(dir,{recursive:true,force:true})
 console.log('Studio DOM: home/direct upload/catalog -> synthesis without analysis/run_id; recommendation import with run_id; filters, retry, empty catalog, polling and 40-color panel passed (AI calls and image pixels mocked)');process.exit(0)
})().catch(e=>{console.error(e);dom.window.close();process.exit(1)})
