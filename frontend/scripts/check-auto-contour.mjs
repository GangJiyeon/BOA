// Local-only QA: generate fixtures with MediaPipe, then render all male recipes.
import assert from 'node:assert/strict'
import {readFileSync,writeFileSync,readdirSync} from 'node:fs'
import {resolve,join} from 'node:path'
import ts from 'typescript'
const dir=resolve(process.argv[2]??'.qa-preview/contour')
const compile=name=>ts.transpileModule(readFileSync(new URL(`../src/studio/${name}.ts`,import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2023,module:ts.ModuleKind.ESNext}}).outputText
const url=js=>`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`
const makeupUrl=url(compile('makeup'))
const {prepareFace,renderMakeup,DEFAULT_MAKEUP}=await import(makeupUrl)
const {recommendMakeupLooks}=await import(url(compile('makeup-looks').replace("from './makeup'",`from '${makeupUrl}'`)))
const reports=[]
for(const name of readdirSync(dir).filter(n=>/^남[1-4]$/.test(n))){
 const d=join(dir,name),f=JSON.parse(readFileSync(join(d,'face.json'))),src=new Uint8ClampedArray(readFileSync(join(d,'source.rgba')))
 const image={width:f.width,height:f.height,data:src},face=prepareFace(image,f.points,f.features)
 for(const masks of [face.variants.noseShading,{face:face.featShade,nose:face.noseCorrection,light:face.featHL}])
  for(const mask of Object.values(masks))assert(mask.every(v=>Number.isFinite(v)&&v>=-1e-5&&v<=1.00001),'Valid masks')
 const off=Object.fromEntries(Object.entries(DEFAULT_MAKEUP).map(([p,l])=>[p,{...l,on:false}]))
 const out=new Uint8ClampedArray(src.length);renderMakeup(face,off,out);assert.deepEqual(out,src)
 const neutral=prepareFace(image,f.points)
 if(name==='남1'){
  const strong={...f.features,cheek_width_ratio:.90,cheek_correction:{relative_width:1.6,wide:1,narrow:0},face_shape:'사각형',face_ratios:{...f.features.face_ratios,jaw_cheek:.86}}
  const narrow={...f.features,cheek_width_ratio:.82,cheek_correction:{relative_width:1.3,wide:0,narrow:0},face_shape:'계란형',face_ratios:{...f.features.face_ratios,jaw_cheek:.74}}
  const broad=prepareFace(image,f.points,strong),slim=prepareFace(image,f.points,narrow)
  const sum=m=>m.reduce((a,b)=>a+b,0)
  assert(sum(broad.variants.shading.sculpt)<sum(slim.variants.shading.sculpt)*.55,'Wide cheeks and square jaw must attenuate bone shading')
  assert(sum(broad.variants.highlight.bone)<sum(slim.variants.highlight.bone)*.8,'Wide anatomy must attenuate bone highlights')
  const sharp=recommendMakeupLooks({sex:'male',tone:'neutral',brightness:'medium',faceShape:'oval'},'party')[1].settings
  assert(sharp.noseShading.noseCleft>0&&sharp.shading.cleft>0,'Sharp recipe must include both clefts')
  const withCleft={...off,noseShading:sharp.noseShading,shading:sharp.shading}
  renderMakeup(face,withCleft,out)
  const noCleft=new Uint8ClampedArray(src.length)
  renderMakeup(face,{...withCleft,noseShading:{...sharp.noseShading,noseCleft:0},shading:{...sharp.shading,cleft:0}},noCleft)
  assert(out.some((v,i)=>v!==noCleft[i]),'Recipe clefts must visibly change rendered pixels')
 }

 const looks=['daily','formal','outdoor','party'].flatMap(occasion=>recommendMakeupLooks({sex:'male',tone:'neutral',brightness:'medium',faceShape:'oval'},occasion))
 const report={name,features:f.features,looks:[]}
 for(const [i,look] of looks.entries()){
  renderMakeup(face,look.settings,out);writeFileSync(join(d,`look-${i}.rgba`),out)
  const contour={...off,shading:look.settings.shading,noseShading:look.settings.noseShading,highlight:look.settings.highlight}
  renderMakeup(face,contour,out);writeFileSync(join(d,`contour-${i}.rgba`),out)
  const baseline=new Uint8ClampedArray(src.length);renderMakeup(neutral,contour,baseline)
  let changed=0,diff=0;for(let p=0;p<src.length;p+=4){if(out[p]!==baseline[p]||out[p+1]!==baseline[p+1]||out[p+2]!==baseline[p+2])changed++;diff+=Math.abs(out[p]-src[p])+Math.abs(out[p+1]-src[p+1])+Math.abs(out[p+2]-src[p+2])}
  assert(changed>0,'Analysis must change placement')
  report.looks.push({name:look.name,shape:look.settings.noseShading.shape,analysisPixels:changed,meanChange:diff/(src.length/4*3)})
 }
 // Highlight zero has no residual feature light.
 renderMakeup(face,{...off,highlight:{...DEFAULT_MAKEUP.highlight,on:true,amount:0}},out);assert.deepEqual(out,src)
 reports.push(report)
}
assert.equal(reports.length,4,'All four supplied photos must be tested')
writeFileSync(join(dir,'report.json'),JSON.stringify(reports,null,2));console.log(`Validated ${reports.length} photos × 12 male looks; saved contour and full-look renders.`)
