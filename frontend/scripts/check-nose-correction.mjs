// Stage 1: render the same nose-only setting on all four photos, without recipe effects.
import assert from 'node:assert/strict'
import {readFileSync,writeFileSync} from 'node:fs'
import ts from 'typescript'
const js=ts.transpileModule(readFileSync('src/studio/makeup.ts','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2023,module:ts.ModuleKind.ESNext}}).outputText
const {prepareFace,renderMakeup,DEFAULT_MAKEUP,labToHex}=await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)
for(let n=1;n<=4;n++){
 const dir=`.qa-preview/contour/남${n}`,f=JSON.parse(readFileSync(`${dir}/face.json`)),src=new Uint8ClampedArray(readFileSync(`${dir}/source.rgba`))
 const face=prepareFace({...f,data:src},f.points,f.features),off=Object.fromEntries(Object.entries(DEFAULT_MAKEUP).map(([p,l])=>[p,{...l,on:false}]))
 const palette=face.nosePalette
 assert([...palette.skin,...palette.shadow,palette.depth,...palette.chroma].every(Number.isFinite))
 assert(palette.samples>0,'Real nose photos must provide shadow color samples')
 writeFileSync(`${dir}/nose-palette.json`,JSON.stringify({...palette,skinHex:labToHex(...palette.skin),shadowHex:labToHex(...palette.shadow)},null,2))
 const mask=face.noseCorrection
 if(n===2||n===4)assert(mask.every(v=>Math.abs(v)<1e-5),'Normal noses must not receive automatic narrowing/tip correction')
 const under=f.points[1],roll=Math.atan2((f.points[263][1]-f.points[33][1])*f.height,(f.points[263][0]-f.points[33][0])*f.width)
 // Exclude the nostril / underside region along the local nose axis.
 for(const mask of [...Object.values(face.variants.noseShading),face.noseCorrection]){
  assert(mask.every(v=>Number.isFinite(v)&&v>=-1e-5&&v<=1.00001))
  let maximumBelow=0
  for(let y=0;y<f.height;y++)for(let x=0;x<f.width;x++){
   const below=-(x+.5-under[0]*f.width)*Math.sin(roll)+(y+.5-under[1]*f.height)*Math.cos(roll)
   const across=(x+.5-under[0]*f.width)*Math.cos(roll)+(y+.5-under[1]*f.height)*Math.sin(roll)
   const noseW=Math.hypot((f.points[129][0]-f.points[358][0])*f.width,(f.points[129][1]-f.points[358][1])*f.height)
   if(below>3&&Math.abs(across)<noseW*.12)maximumBelow=Math.max(maximumBelow,mask[y*f.width+x])
  }
  assert(maximumBelow<.01,'Nose shading must protect the central underside without erasing the outer wings')
 }
 // Both lower outer wings must retain measurable shadow after clipping.
 for(const id of [64,294]){
  const x=Math.round(f.points[id][0]*f.width),y=Math.round(f.points[id][1]*f.height)
  let peak=0
  for(let dy=-2;dy<=2;dy++)for(let dx=-2;dx<=2;dx++)peak=Math.max(peak,face.variants.noseShading.wings[(y+dy)*f.width+x+dx]??0)
  assert(peak>.08,'Outer-wing shading must survive the underside protection')
 }
 // Ref diagrams: a deliberate bridge gap and a bright tip center with darker side faces.
 const gap=[(f.points[6][0]*.55+f.points[195][0]*.45)*f.width,(f.points[6][1]*.55+f.points[195][1]*.45)*f.height]
 const gx=Math.round(gap[0]),gy=Math.round(gap[1])
 let gapPeak=0
 for(let dx=-20;dx<=20;dx++)gapPeak=Math.max(gapPeak,face.variants.noseShading.sculpted[gy*f.width+gx+dx]??0)
 assert(gapPeak<.02,'Bridge shading must contain a visible break')
 const out=new Uint8ClampedArray(src.length)
 for(const [label,amount] of [['standard',.5],['strong',.8]]){
  renderMakeup(face,{...off,noseShading:{...DEFAULT_MAKEUP.noseShading,on:true,shape:'sculpted',amount}},out)
  writeFileSync(`${dir}/nose-${label}.rgba`,out)
 }
 renderMakeup(face,{...off,noseShading:{...DEFAULT_MAKEUP.noseShading,on:true,shape:'sculpted',amount:.65},highlight:{...DEFAULT_MAKEUP.highlight,on:true,shape:'tzone',amount:.25}},out)
 writeFileSync(`${dir}/nose-reference.rgba`,out)
 const shade=face.variants.noseShading.sculpted,light=face.noseAccent
 writeFileSync(`${dir}/nose-reference-shade.f32`,Buffer.from(shade.buffer,shade.byteOffset,shade.byteLength))
 writeFileSync(`${dir}/nose-reference-light.f32`,Buffer.from(light.buffer,light.byteOffset,light.byteLength))
 console.log(`남${n}: valid nose masks, protected underside${n===2||n===4?', normal-nose correction off':''}`)
}
