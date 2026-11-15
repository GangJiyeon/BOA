import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'
const js=ts.transpileModule(readFileSync('src/studio/makeup.ts','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2023,module:ts.ModuleKind.ESNext}}).outputText
const {sampleNosePalette}=await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)
const points=Array.from({length:478},()=>[60,60])
const lit=[6,197,195,5,4],sides=[122,351,196,419,3,248,51,281,45,275,49,279,48,278]
points[129]=[10,100];points[358]=[110,100]
for(const [i,id] of lit.entries())points[id]=[15+i*20,15]
for(const [i,id] of sides.entries())points[id]=[10+(i%7)*16,45+Math.floor(i/7)*20]
function fixture(skin,shadow){
 const data=new Uint8ClampedArray(120*120*4)
 for(let i=0;i<data.length;i+=4)data.set([...skin,255],i)
 for(const id of sides){const [cx,cy]=points[id];for(let y=cy-5;y<=cy+5;y++)for(let x=cx-5;x<=cx+5;x++)data.set([...shadow,255],(y*120+x)*4)}
 return {width:120,height:120,data}
}
const warm=fixture([205,160,128],[178,136,109]),cool=fixture([185,159,163],[155,131,139])
const a=sampleNosePalette(warm,points),b=sampleNosePalette(cool,points)
assert(a.samples>0&&b.samples>0)
assert(a.skin[2]>b.skin[2]+10,'Sampled nose color must follow the user photo')
assert(a.shadow[0]<a.skin[0]&&b.shadow[0]<b.skin[0])
assert([...a.chroma,...b.chroma].every(v=>Math.abs(v)<=2.5),'Do not amplify saturation from side lighting')
const dirty=fixture([205,160,128],[178,136,109])
for(const [id,color] of [[sides[0],[2,2,2]],[sides[1],[240,60,60]],[sides[2],[255,255,255]]]){
 const [cx,cy]=points[id];for(let y=cy-5;y<=cy+5;y++)for(let x=cx-5;x<=cx+5;x++)dirty.data.set([...color,255],(y*120+x)*4)
}
const c=sampleNosePalette(dirty,points)
for(let i=0;i<3;i++)assert(Math.abs(c.shadow[i]-a.shadow[i])<1,'Nostril darkness, redness and glare must not determine shadow color')
const empty=sampleNosePalette({width:120,height:120,data:new Uint8ClampedArray(120*120*4)},points)
assert.equal(empty.depth,0)
assert(Object.values(empty).flat().every(Number.isFinite))
console.log('Nose palette: photo-specific tint, robust shadow sampling, bounded chroma and transparent fallback passed.')
