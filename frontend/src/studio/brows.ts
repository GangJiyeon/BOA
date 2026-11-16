import type { FaceLite, PreparedFace, Pt, BrowRegion } from './makeup'
export type BrowAsset = {
  id: string; label: string; group: string; preview: string
  left: { url: string; width: number; height: number }
  right: { url: string; width: number; height: number }
}
export type BrowSettings = { on: boolean; amount: number; width: number; thickness: number; vertical: number; spread: number; hex: string }
export const DEFAULT_BROWS: BrowSettings = { on: true, amount: 0.8, width: 1.2, thickness: 1.35, vertical: -0.75, spread: 0, hex: '#55443c' }
export type BrowImages = { left: ImageBitmap; right: ImageBitmap }
const BROW_ALPHA_TARGET = 200
const tintCache = new WeakMap<ImageBitmap, {hex:string;canvas:HTMLCanvasElement}>()
function tintedBrow(source:ImageBitmap,hex:string) {
  const cached=tintCache.get(source);if(cached?.hex===hex)return cached.canvas
  const canvas=document.createElement('canvas');canvas.width=source.width;canvas.height=source.height
  const ctx=canvas.getContext('2d')!;ctx.drawImage(source,0,0)
  const pixels=ctx.getImageData(0,0,source.width,source.height),data=pixels.data,n=parseInt(hex.slice(1),16)
  const color=[n>>16&255,n>>8&255,n&255]
  // 에셋마다 털 불투명도가 달라(소프트 아치·일자는 남성 눈썹의 1/3 수준이라 털이 거의 투명해짐)
  // 진한 털(상위 10%) 불투명도를 ALPHA_TARGET에 맞춰 늘림
  const alphas:number[]=[]
  for(let i=3;i<data.length;i+=16)if(data[i]>10)alphas.push(data[i])
  alphas.sort((x,y)=>x-y)
  const gain=Math.min(4,Math.max(1,BROW_ALPHA_TARGET/(alphas[Math.floor(alphas.length*.9)]??BROW_ALPHA_TARGET)))
  for(let i=0;i<data.length;i+=4){
    data[i+3]=Math.min(255,data[i+3]*gain)
    const light=(data[i]*.2126+data[i+1]*.7152+data[i+2]*.0722)/255
    // 밝은 바탕은 투명하게 비우고 어두운 털 가닥만 살린다.
    // 밝은 픽셀을 흰색으로 칠하면 피부 위에 불투명한 덩어리처럼 보인다.
    data[i+3]*=Math.max(.12,Math.min(.95,1.05-light*1.6))
    // 밝게 띄우면 원래 눈썹보다 연한 회갈색이 됨 → 털 가닥은 고른 색 그대로, 옅은 가닥만 살짝 밝게
    for(let c=0;c<3;c++)data[i+c]=Math.min(255,color[c]*(.9+light*.35))
  }
  ctx.putImageData(pixels,0,0);tintCache.set(source,{hex,canvas});return canvas
}
export function browPlacement(points: readonly Pt[], side: 'left' | 'right', image: { width: number; height: number }, settings: BrowSettings, _region?: BrowRegion) {
  const left = side === 'left'
  // 원본 눈썹 위·아래 윤곽 10점을 얼굴 회전에 맞춰 투영한다.
  // 눈썹 영역과 에셋의 중심을 맞추고 원본 종횡비를 유지한다.
  const indexes = left ? [70,63,105,66,107,55,65,52,53,46] : [336,296,334,293,300,276,283,282,295,285]
  const faceWidth = Math.hypot(points[454][0]-points[234][0], points[454][1]-points[234][1])
  const angle = Math.atan2(points[263][1]-points[33][1], points[263][0]-points[33][0])
  const cos = Math.cos(angle), sin = Math.sin(angle)
  const contour = indexes.map(i => [points[i][0]*cos+points[i][1]*sin, -points[i][0]*sin+points[i][1]*cos])
  const xs = contour.map(p=>p[0]), ys = contour.map(p=>p[1])
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys)
  const cx = (minX+maxX)/2, cy = (minY+maxY)/2
  const baseWidth = Math.max(1,maxX-minX)
  const width = baseWidth*settings.width
  const height = baseWidth*image.height/Math.max(1,image.width)*settings.thickness
  const spread = (left ? -1 : 1)*settings.spread*faceWidth/100, vertical = settings.vertical*faceWidth/100
  return { x: cx*cos-cy*sin+spread*cos-vertical*sin,
    y: cx*sin+cy*cos+spread*sin+vertical*cos,
    width, height, angle }
}
// fill: 원래 눈썹을 지우지 않고 빈 곳만 채움 (남성) — 'darken' 합성이라 원래보다 밝은 곳(숱이 빈 곳)에만 눈썹 색이 들어가고 이미 진한 곳은 그대로
export function drawBrows(ctx: CanvasRenderingContext2D, face: FaceLite, images: BrowImages, settings: BrowSettings, fill = false) {
  if (!settings.on || settings.amount <= 0) return
  ctx.save()
  if (fill) ctx.globalCompositeOperation = 'darken'
  for (const side of ['left','right'] as const) {
    const source = images[side], placement = browPlacement(face.points,side,source,settings,face.browRegions?.[side])
    // 반투명한 털결 사이로 피부가 비치도록 합성한다.
    const tinted = tintedBrow(source,settings.hex)
    ctx.save();ctx.globalAlpha=settings.amount;ctx.translate(placement.x,placement.y);ctx.rotate(placement.angle)
    ctx.drawImage(tinted,-placement.width/2,-placement.height/2,placement.width,placement.height);ctx.restore()
  }
  ctx.restore()
}
export async function loadBrowImages(asset: BrowAsset, signal: AbortSignal): Promise<BrowImages> {
  const loaded: ImageBitmap[]=[]
  try {
    const results=await Promise.allSettled((['left','right'] as const).map(async side=>{
      const response=await fetch(asset[side].url,{signal})
      if(!response.ok) throw new Error('눈썹 이미지를 불러오지 못했습니다.')
      const bitmap=await createImageBitmap(await response.blob());loaded.push(bitmap);return bitmap
    }))
    const failure=results.find(r=>r.status==='rejected')
    if(failure?.status==='rejected') throw failure.reason
    if(signal.aborted) throw new DOMException('Aborted','AbortError')
    return {left:(results[0] as PromiseFulfilledResult<ImageBitmap>).value,right:(results[1] as PromiseFulfilledResult<ImageBitmap>).value}
  } catch(error) { loaded.forEach(bitmap=>bitmap.close());throw error }
}

// 사진 속 원래 눈썹 색: 눈썹 윤곽 안에서 가장 어두운 15% 픽셀 평균 (밝은 쪽은 피부가 섞임)
// 밝기는 범위로만 묶음: 너무 밝으면(옅은 눈썹·피부 섞임) 상한까지 낮추고, 너무 어두우면 새카만 덩어리가 되어 하한까지 올림
const BROW_IDS = [[70, 63, 105, 66, 107, 55, 65, 52, 53, 46], [336, 296, 334, 293, 300, 276, 283, 282, 295, 285]]
const BROW_LUMA_MIN = 28, BROW_LUMA_MAX = 85, FALLBACK_BROW = '#55443c'
const browColorCache = new WeakMap<PreparedFace, string>()
export function browColor(face: PreparedFace) {
  const cached = browColorCache.get(face)
  if (cached) return cached
  const { width: w, height: h, src, points } = face
  const samples: [number, number, number, number][] = []
  for (const ids of BROW_IDS) {
    const poly = ids.map(i => points[i])
    const xs = poly.map(p => p[0]), ys = poly.map(p => p[1])
    for (let y = Math.max(0, Math.floor(Math.min(...ys))); y <= Math.min(h - 1, Math.ceil(Math.max(...ys))); y++) {
      for (let x = Math.max(0, Math.floor(Math.min(...xs))); x <= Math.min(w - 1, Math.ceil(Math.max(...xs))); x++) {
        let inside = false
        for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
          const [xi, yi] = poly[i], [xj, yj] = poly[j]
          if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside
        }
        if (!inside) continue
        const o = (y * w + x) * 4, r = src[o], g = src[o + 1], b = src[o + 2]
        samples.push([r * .299 + g * .587 + b * .114, r, g, b])
      }
    }
  }
  let hex = FALLBACK_BROW
  if (samples.length >= 20) {
    samples.sort((a, b) => a[0] - b[0])
    const dark = samples.slice(0, Math.max(10, Math.floor(samples.length * .15)))
    const mean = [1, 2, 3].map(c => dark.reduce((sum, v) => sum + v[c], 0) / dark.length)
    const luma = mean[0] * .299 + mean[1] * .587 + mean[2] * .114
    const target = Math.min(BROW_LUMA_MAX, Math.max(BROW_LUMA_MIN, luma))
    hex = '#' + mean.map(v => Math.min(255, Math.round(v * target / Math.max(1, luma))).toString(16).padStart(2, '0')).join('')
  }
  browColorCache.set(face, hex)
  return hex
}
