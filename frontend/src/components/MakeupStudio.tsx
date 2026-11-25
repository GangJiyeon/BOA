import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { prepareMakeupPhoto } from '../api/makeup'
import { DEFAULT_MAKEUP, MAKEUP_SHAPES, type FaceLite, type MakeupPart, type MakeupSettings, type ShapeFeatures } from '../studio/makeup'
import type { WorkerRequest, WorkerResponse } from '../studio/makeup-worker'
import { customSwatches, occasionsFor, recommendMakeupLooks, type FaceShape, type MakeupOccasion, type LookId, type MakeupProfile } from '../studio/makeup-looks'
import { computeFit, fitSummary } from '../studio/face-fit'
import type { MakeupPreparation } from '../api/makeup'

import { makeBrowStyles } from '../studio/brow-styles'
import { DEFAULT_LASHES, drawLashes, loadLashImages, type LashAsset, type LashImages, type LashSettings } from '../studio/lashes'
import { DEFAULT_BROWS, drawBrows, loadBrowImages, type BrowAsset, type BrowImages, type BrowSettings } from '../studio/brows'

const PART_LABELS: Record<MakeupPart, string> = { skin:'피부 보정', lip:'립', blush:'블러셔', eyeshadow:'아이섀도우', shadowPoint:'눈꼬리 포인트', underShadow:'아래 눈가', aegyo:'애교살', eyeliner:'아이라인', shading:'턱 쉐딩', noseShading:'코 쉐딩', highlight:'하이라이터' }
const PARTS = Object.keys(PART_LABELS) as MakeupPart[]
const INITIAL_BROWS: BrowSettings = {...DEFAULT_BROWS,on:false}
const OWN_BROW_AMOUNT = .3
// 추천 룩 화면의 강도 묶음 (부위 11개를 5개로)
const GROUPS = [
  {id:'base',label:'베이스',parts:['skin']},
  {id:'contour',label:'윤곽',parts:['shading','noseShading','highlight']},
  {id:'blush',label:'블러셔',parts:['blush']},
  {id:'eye',label:'눈',parts:['eyeshadow','shadowPoint','underShadow','aegyo','eyeliner']},
  {id:'lip',label:'립',parts:['lip']},
] as const satisfies readonly {id:string;label:string;parts:readonly MakeupPart[]}[]
// 직접 꾸미기 부위 순서 (얼굴 아래층부터) · 켤 때 기본 강도
const CUSTOM_ORDER = ['shading','noseShading','highlight','blush','eyeshadow','shadowPoint','underShadow','aegyo','eyeliner','lip'] as const
const CUSTOM_AMOUNT = .5
const INITIAL_AMOUNTS = Object.fromEntries(PARTS.map(part=>[part,1])) as Record<MakeupPart,number>
async function loadImage(file: File) {
  const bitmap=await createImageBitmap(file),scale=Math.min(1,1280/Math.max(bitmap.width,bitmap.height))
  const canvas=document.createElement('canvas');canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale)
  const ctx=canvas.getContext('2d',{willReadFrequently:true})
  if(!ctx) { bitmap.close();throw new Error('이 브라우저에서는 메이크업 체험을 사용할 수 없습니다.') }
  ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close()
  const image=ctx.getImageData(0,0,canvas.width,canvas.height)
  const blob=await new Promise<Blob>((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(new Error('사진을 준비하지 못했습니다.')),'image/png'))
  return {image,blob}
}
async function decodeCleanedImage(encoded:string,width:number,height:number) {
  const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0))
  const bitmap=await createImageBitmap(new Blob([bytes],{type:'image/png'}))
  try {
    if(bitmap.width!==width||bitmap.height!==height)throw new Error('눈썹 보정 이미지 크기가 다릅니다.')
    const buffer=document.createElement('canvas');buffer.width=width;buffer.height=height
    const ctx=buffer.getContext('2d')!;ctx.drawImage(bitmap,0,0)
    return ctx.getImageData(0,0,width,height).data
  } finally {bitmap.close()}
}
// 속도: 화장은 얼굴 윤곽 안에만 그려져 얼굴 주변만 잘라 계산 (사진 전체 대비 계산량 절반 이하), 룩 카드는 작은 사본으로
const CROP_MARGIN = .12, PREVIEW_SIDE = 320
type Crop = { x0: number; y0: number; width: number; height: number; data: Uint8ClampedArray; cleaned: Uint8ClampedArray; points: [number, number][]; preview: { width: number; height: number; data: Uint8ClampedArray; cleaned: Uint8ClampedArray } }
function cropFace(image: ImageData, cleaned: Uint8ClampedArray, points: readonly (readonly number[])[]): Crop {
  const W = image.width, H = image.height, xs = points.map(p => p[0] * W), ys = points.map(p => p[1] * H)
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys), m = (maxX - minX) * CROP_MARGIN
  const x0 = Math.max(0, Math.floor(minX - m)), y0 = Math.max(0, Math.floor(minY - m)), x1 = Math.min(W, Math.ceil(maxX + m)), y1 = Math.min(H, Math.ceil(maxY + m))
  const width = x1 - x0, height = y1 - y0
  const cut = (src: Uint8ClampedArray) => { const out = new Uint8ClampedArray(width * height * 4); for (let y = 0; y < height; y++) out.set(src.subarray(((y0 + y) * W + x0) * 4, ((y0 + y) * W + x1) * 4), y * width * 4); return out }
  const data = cut(image.data), cut2 = cut(cleaned)
  const scale = Math.min(1, PREVIEW_SIDE / Math.max(width, height)), pw = Math.max(1, Math.round(width * scale)), ph = Math.max(1, Math.round(height * scale))
  const shrink = (src: Uint8ClampedArray) => {
    const a = document.createElement('canvas'); a.width = width; a.height = height; a.getContext('2d')!.putImageData(new ImageData(src.slice(), width, height), 0, 0)
    const b = document.createElement('canvas'); b.width = pw; b.height = ph; const ctx = b.getContext('2d', { willReadFrequently: true })!
    ctx.imageSmoothingQuality = 'high'; ctx.drawImage(a, 0, 0, pw, ph); return ctx.getImageData(0, 0, pw, ph).data
  }
  return { x0, y0, width, height, data, cleaned: cut2, points: points.map(p => [(p[0] * W - x0) / width, (p[1] * H - y0) / height]), preview: { width: pw, height: ph, data: shrink(data), cleaned: shrink(cut2) } }
}
// 컬러 피커: 끌 때마다 바꾸지 않고 피커를 닫거나 확인하면 적용 (네이티브 change 이벤트)
function ColorPick({ value, disabled, label, onPick }: { value: string; disabled?: boolean; label: string; onPick: (hex: string) => void }) {
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => {
    const el = ref.current; if (!el) return
    el.value = value
    const commit = () => onPick(el.value)
    el.addEventListener('change', commit)
    return () => el.removeEventListener('change', commit)
  }, [value, onPick])
  return <input ref={ref} type="color" defaultValue={value} disabled={disabled} aria-label={label} title="고른 뒤 닫으면 적용돼요" />
}
type Frame = { token: number; width: number; height: number; data: Uint8ClampedArray }
type Lite = FaceLite & { token: number; eyeFit: number; lipPale: number; browHex: string }
function LookPreview({frame,face,browImages,brows,lash,browFill}:{frame:Frame|undefined;face:Lite|null;browImages:BrowImages|null;brows:BrowSettings;browFill:boolean;lash:{catalog:LashAsset[];images:LashImages;settings:LashSettings}}) {
  const ref=useRef<HTMLCanvasElement>(null)
  useEffect(()=>{
    const el=ref.current;if(!el)return
    el.width=240;el.height=240
    if(!face||!frame||frame.token!==face.token)return
    const buffer=document.createElement('canvas');buffer.width=frame.width;buffer.height=frame.height
    const ctx=buffer.getContext('2d')!;ctx.putImageData(new ImageData(new Uint8ClampedArray(frame.data),frame.width,frame.height),0,0)
    if(browImages)drawBrows(ctx,face,browImages,brows,browFill)
    drawLashes(ctx,face,lash.catalog,lash.images,lash.settings)
    const side=Math.min(frame.width,frame.height),x=(frame.width-side)/2,y=(frame.height-side)/2
    el.getContext('2d')!.drawImage(buffer,x,y,side,side,0,0,240,240)
  },[frame,face,browImages,brows,lash,browFill])
  return <canvas ref={ref} aria-label="추천 메이크업 미리보기" />
}
export default function MakeupStudio({file,profile}:{file:File|null;profile:MakeupProfile}) {
  const canvas=useRef<HTMLCanvasElement>(null)
  // 사진·분석 원본만 저장, 얼굴 준비(prepareFace)는 얼굴형을 바꾸면 다시 (자동이면 분석한 얼굴형)
  const [loadedFace,setLoadedFace]=useState<{file:File;image:ImageData;response:MakeupPreparation;cleaned:Uint8ClampedArray}|null>(null)
  const [mode,setMode]=useState<'look'|'custom'>('look')
  const [faceError,setFaceError]=useState<{file:File;message:string}|null>(null),[holding,setHolding]=useState(false)
  const error=(faceError?.file===file?faceError.message:'')
  const occasions=occasionsFor(profile.sex)
  const [picked,setOccasion]=useState<MakeupOccasion>('daily')
  // 성별을 바꿔 없는 상황이면 데일리로
  const occasionInfo=occasions.find(item=>item.id===picked)??occasions[0]
  const occasion=occasionInfo.id
  // profile은 매 렌더 새 객체라 값으로 의존
  const {tone,brightness,sex}=profile
  const loaded=loadedFace?.file===file?loadedFace:null
  const fit=useMemo(()=>loaded?computeFit(loaded.response.features):null,[loaded])
  const faceShape:FaceShape=profile.faceShape==='auto'?fit?.face??'oval':profile.faceShape
  // 얼굴 준비·렌더는 워커에서 (메인 스레드가 수 초씩 멈추던 원인)
  const crop=useMemo(()=>loaded?cropFace(loaded.image,loaded.cleaned,loaded.response.points):null,[loaded])
  const features=useMemo<ShapeFeatures|null>(()=>{
    const f=loaded?.response.features
    return f?{...f.nose_ratios,cheek_width_ratio:f.cheek_width_ratio,cheek_correction:f.cheek_correction,nose_correction:f.nose_correction,face_shape:f.face_shape,face_ratios:f.face_ratios,fit:fit&&{...fit,face:faceShape}}:null
  },[loaded,fit,faceShape])
  const worker=useRef<Worker|null>(null),tokenRef=useRef(0)
  const [faces,setFaces]=useState<{main:Lite|null;preview:Lite|null}>({main:null,preview:null})
  const [frames,setFrames]=useState<Record<string,Frame>>({})
  const [workerError,setWorkerError]=useState('')
  useEffect(()=>{
    const w=new Worker(new URL('../studio/makeup-worker.ts',import.meta.url),{type:'module'})
    w.onmessage=(event:MessageEvent<WorkerResponse>)=>{
      const msg=event.data
      if(msg.token!==tokenRef.current)return
      if(msg.type==='prepared')setFaces(current=>({...current,[msg.target]:{...msg.lite,token:msg.token,eyeFit:msg.eyeFit,lipPale:msg.lipPale,browHex:msg.browHex}}))
      else if(msg.type==='rendered')setFrames(current=>({...current,[msg.key]:{token:msg.token,width:msg.width,height:msg.height,data:msg.data}}))
      else setWorkerError(msg.message)
    }
    worker.current=w
    return()=>{w.terminate();worker.current=null}
  },[])
  const post=useCallback((msg:WorkerRequest)=>worker.current?.postMessage(msg),[])
  useEffect(()=>{
    if(!crop)return
    const token=++tokenRef.current
    setFaces({main:null,preview:null});setFrames({});setWorkerError('')
    post({type:'prepare',token,target:'main',image:{width:crop.width,height:crop.height,data:crop.data},cleaned:crop.cleaned,points:crop.points,features})
    post({type:'prepare',token,target:'preview',image:{width:crop.preview.width,height:crop.preview.height,data:crop.preview.data},cleaned:crop.preview.cleaned,points:crop.points,features})
  },[crop,features,post])
  const browRegions=useMemo(()=>{
    const r=loaded?.response.brow_regions;if(!r||!crop)return undefined
    return Object.fromEntries(Object.entries(r).map(([k,v])=>[k,v&&{...v,x:v.x-crop.x0,y:v.y-crop.y0}])) as FaceLite['browRegions']
  },[loaded,crop])
  const face=useMemo<Lite|null>(()=>faces.main&&{...faces.main,browRegions},[faces.main,browRegions])
  const previewFace=faces.preview
  // 입술이 창백한 사진은 립 베이지를 덜 섞고 강도를 살짝 올림 (워커에서 잰 값)
  const lipPale=face?.lipPale??0
  // 쿠션은 매번 새 객체로 와서 값(호수·베이스)으로 고정 (객체 기준이면 룩 추천이 매 렌더 다시 계산)
  const cushionShade=profile.cushion?.shade,cushionBase=profile.cushion?.base
  const looks=useMemo(()=>{
    const cushion=cushionShade!==undefined&&cushionBase!==undefined?{shade:cushionShade,base:cushionBase}:undefined
    return recommendMakeupLooks({tone,brightness,faceShape,sex,lipPale,cushion},occasion)
  },[tone,brightness,faceShape,sex,occasion,lipPale,cushionShade,cushionBase])
  const [selectedId,setSelectedId]=useState<LookId>('daily-light'),[intensity,setIntensity]=useState(1)
  // 속눈썹: 고르기 전에는 룩 값
  // 사진별 눈 화장 기본값: 사용자 눈매(속눈썹 라인)가 연하면 아이라인·섀도·속눈썹 기본 강도를 낮춤 (슬라이더에도 그 값이 보임)
  const eyeFit=face?.eyeFit??1
  const fitLook=useMemo(()=>{
    const shadowFit=.55+.45*eyeFit
    return (look:MakeupSettings):MakeupSettings=>({...look,
      eyeliner:{...look.eyeliner,amount:look.eyeliner.amount*eyeFit},
      eyeshadow:{...look.eyeshadow,amount:look.eyeshadow.amount*shadowFit},
      shadowPoint:{...look.shadowPoint,amount:look.shadowPoint.amount*shadowFit},
      underShadow:{...look.underShadow,amount:look.underShadow.amount*shadowFit},
      aegyo:{...look.aegyo,amount:look.aegyo.amount*shadowFit}})
  },[eyeFit])
  // 속눈썹: 고르기 전에는 룩 값, 강도는 직접 바꾸기 전까지 사진별 기본값
  const [lashPicked,setLashAmount]=useState<number|null>(null),[lowerPicked,setLowerAmount]=useState<number|null>(null)
  const lashAmount=lashPicked??Math.round(DEFAULT_LASHES.amount*eyeFit*100)/100,lowerAmount=lowerPicked??Math.round(DEFAULT_LASHES.lower*eyeFit*100)/100
  const [lashCatalog,setLashCatalog]=useState<LashAsset[]>([]),[lashImages,setLashImages]=useState<LashImages>({})
  const [amounts,setAmounts]=useState(INITIAL_AMOUNTS)
  const selected=looks.find(look=>look.id===selectedId)??looks[0]
  const lashes=useMemo<LashSettings>(()=>({style:selected.lashes,amount:lashAmount,lower:lowerAmount}),[lashAmount,lowerAmount,selected.lashes])
  // 룩 카드 미리보기용 (속눈썹 종류별 고정 객체, 매 렌더 새 객체면 미리보기를 계속 다시 그림)
  const previewLash=useMemo(()=>{
    const make=(style:string)=>({catalog:lashCatalog,images:lashImages,settings:{...DEFAULT_LASHES,amount:DEFAULT_LASHES.amount*eyeFit,lower:DEFAULT_LASHES.lower*eyeFit,style}})
    return Object.fromEntries(['none',...lashCatalog.map(a=>a.id)].map(id=>[id,make(id)])) as Record<string,ReturnType<typeof make>>
  },[lashCatalog,lashImages,eyeFit])
  const base=useMemo(()=>fitLook(selected.settings),[fitLook,selected.settings])
  // 룩 카드 미리보기도 사진별 기본값으로 (매 렌더 새 객체면 미리보기를 계속 다시 그림)
  const fittedLooks=useMemo(()=>Object.fromEntries(looks.map(look=>[look.id,fitLook(look.settings)])) as Record<LookId,MakeupSettings>,[looks,fitLook])
  // 추천 룩: 룩 설정 × 전체 강도 × 묶음 강도 (모양·색은 룩 그대로)
  const lookSettings=useMemo(()=>Object.fromEntries(PARTS.map(part=>[part,{...base[part],on:base[part].on&&amounts[part]>0,amount:Math.min(1,base[part].amount*intensity*amounts[part])}])) as MakeupSettings,[base,intensity,amounts])
  // 직접 꾸미기: 룩과 따로, 맨얼굴(피부 보정만)에서 시작해 부위마다 켜기·종류·색·강도를 고름
  const swatches=useMemo(()=>customSwatches({tone,brightness}),[tone,brightness])
  const blankCustom=useMemo(()=>Object.fromEntries(PARTS.map(part=>[part,part==='skin'?selected.settings.skin:{on:false,hex:swatches[part][0]??DEFAULT_MAKEUP[part].hex,amount:CUSTOM_AMOUNT,shape:DEFAULT_MAKEUP[part].shape}])) as MakeupSettings,[selected.settings.skin,swatches])
  const [customPicked,setCustom]=useState<MakeupSettings|null>(null)
  const custom=customPicked??blankCustom
  const [customLash,setCustomLash]=useState<LashSettings|null>(null)
  const customLashes=customLash??{style:'none',amount:Math.round(DEFAULT_LASHES.amount*eyeFit*100)/100,lower:Math.round(DEFAULT_LASHES.lower*eyeFit*100)/100}
  const updateCustom=<P extends MakeupPart>(part:P,patch:Partial<MakeupSettings[P]>)=>setCustom(current=>{const c=current??blankCustom;return {...c,[part]:{...c[part],...patch}}})
  const settings=mode==='custom'?custom:lookSettings
  const renderLashes=mode==='custom'?customLashes:lashes
  // 직접 꾸미기는 전체 강도를 곱하지 않음
  const scale=mode==='custom'?1:intensity
  const [catalog,setCatalog]=useState<BrowAsset[]>([]),[chosenAssetId,setAssetId]=useState<string|null>(null)
  // 고른 성별의 눈썹을 앞에, 직접 고르기 전에는 그중 첫 번째
  const browGroup=profile.sex==='male'?'남성형':'여성형'
  // 남성은 눈썹을 갈아 끼우지 않고 원래 눈썹의 빈 곳만 채움 (교체하면 인상이 바뀜)
  const browFill=profile.sex==='male'
  // 여성: 모양을 고르기 전에는 에셋 없이 내 눈썹 모양 그대로 빈 곳만 채움 (워커에서), 모양을 고르면 교체
  const ownFill=profile.sex==='female'&&chosenAssetId===null
  const assets=useMemo(()=>[...catalog].sort((a,b)=>Number(b.group===browGroup)-Number(a.group===browGroup)),[catalog,browGroup])
  // 룩 기본 눈썹: 직접 고르기 전에는 룩에 정한 눈썹을 켜서 보여 줌 (남성 룩)
  const [browTouched,setBrowTouched]=useState(false)
  const assetId=chosenAssetId??(browTouched?undefined:selected.brow)??assets[0]?.id??''
  const [browState,setBrows]=useState<BrowSettings>(INITIAL_BROWS)
  // 내 눈썹 채우기 농도는 따로 (기본 30%, 교체 눈썹 기본 80%와 섞이지 않게)
  const [ownAmount,setOwnAmount]=useState(OWN_BROW_AMOUNT)
  const setBrowAmount=(v:number)=>{if(ownFill){setBrowTouched(true);setOwnAmount(v)}else updateBrows(current=>({...current,amount:v}))}
  // 눈썹 색: 직접 고르기 전에는 사진 속 원래 눈썹 색
  const [browHex,setBrowHex]=useState<string|null>(null)
  const updateBrows=(next:BrowSettings|((current:BrowSettings)=>BrowSettings))=>{setBrowTouched(true);setBrows(next)}
  const brows=useMemo(()=>({...browState,on:browState.on||(!browTouched&&(Boolean(selected.brow)||ownFill)),amount:ownFill?ownAmount:browState.amount,hex:browHex??face?.browHex??browState.hex}),[browState,browTouched,selected.brow,ownFill,ownAmount,browHex,face])
  const [loadedBrows,setLoadedBrows]=useState<{id:string;images:BrowImages}|null>(null)
  const [browFailure,setBrowFailure]=useState<{id:string;message:string}|null>(null)
  const styles=useMemo(()=>makeBrowStyles(assets),[assets])
  const asset=assets.find(item=>item.id===assetId)
  // 내 눈썹 채우기 중에는 에셋을 그리지 않음
  const browImages=!ownFill&&loadedBrows?.id===assetId?loadedBrows.images:null
  const browError=browFailure&&(browFailure.id===assetId||browFailure.id==='catalog')?browFailure.message:''
  useEffect(()=>{
    // 속눈썹은 몇 종뿐이라 처음에 다 불러둠
    const controller=new AbortController(),opened:ImageBitmap[]=[]
    void fetch('/static/makeup/lashes/catalog.json',{signal:controller.signal,cache:'no-store'}).then(async r=>{
      if(!r.ok)throw new Error('속눈썹 목록을 불러오지 못했습니다.')
      const catalog:LashAsset[]=await r.json()
      const loaded=await Promise.all(catalog.map(async asset=>{const images=await loadLashImages(asset,controller.signal);opened.push(images.left,images.right,...(images.lower?[images.lower.left,images.lower.right]:[]));return [asset.id,images] as const}))
      if(!controller.signal.aborted){setLashCatalog(catalog);setLashImages(Object.fromEntries(loaded))}
    }).catch(()=>{/* 속눈썹 없이도 메이크업은 동작 */})
    return()=>{controller.abort();opened.forEach(bitmap=>bitmap.close())}
  },[])
  useEffect(()=>{
    const controller=new AbortController()
    void fetch('/static/makeup/brows/catalog.json',{signal:controller.signal,cache:'no-store'}).then(async r=>{
      if(!r.ok)throw new Error('눈썹 목록을 불러오지 못했습니다.')
      const result:BrowAsset[]=await r.json()
      if(!controller.signal.aborted)setCatalog(result)
    }).catch(err=>{if(!controller.signal.aborted)setBrowFailure({id:'catalog',message:String(err)})})
    return()=>controller.abort()
  },[])
  useEffect(()=>{
    if(!asset)return
    const controller=new AbortController();let current:BrowImages|null=null
    void loadBrowImages(asset,controller.signal).then(images=>{
      if(controller.signal.aborted){images.left.close();images.right.close();return}
      current=images;setLoadedBrows({id:asset.id,images});setBrowFailure(null)
    }).catch(err=>{if(!controller.signal.aborted)setBrowFailure({id:asset.id,message:String(err)})})
    return()=>{controller.abort();current?.left.close();current?.right.close()}
  },[asset])
  useEffect(()=>{
    if(!file)return
    const controller=new AbortController()
    void (async()=>{
      const {image,blob}=await loadImage(file)
      if(controller.signal.aborted)return
      const response=await prepareMakeupPhoto(blob,controller.signal)
      const cleaned=await decodeCleanedImage(response.brow_base_png,image.width,image.height)
      if(!controller.signal.aborted){setLoadedFace({file,image,response,cleaned});setFaceError(null)}
    })().catch(err=>{if(!controller.signal.aborted)setFaceError({file,message:err instanceof Error?err.message:'얼굴을 분석하지 못했습니다.'})})
    return()=>controller.abort()
  },[file])
  // 눈썹 교체(여성): 원래 눈썹을 지운 사진을 섞는 비율 (워커에서 섞음)
  const browWeight=browImages&&!browFill&&brows.on&&brows.amount>0?Math.min(1,scale)*Math.min(1,brows.amount/.3):0
  // 값이 같으면 같은 객체 (워커 렌더 요청이 매 렌더 다시 가지 않게)
  const ownBrow=useMemo(()=>ownFill&&brows.on&&brows.amount>0?{amount:Math.min(1,brows.amount*scale),hex:brows.hex}:undefined,[ownFill,brows.on,brows.amount,brows.hex,scale])
  const ownBrowPreview=useMemo(()=>ownFill&&brows.on&&brows.amount>0?{amount:brows.amount,hex:brows.hex}:undefined,[ownFill,brows.on,brows.amount,brows.hex])
  useEffect(()=>{if(face)post({type:'render',key:'main',target:'main',settings,browWeight,browFill:ownBrow})},[face,settings,browWeight,ownBrow,post])
  useEffect(()=>{
    if(!previewFace||mode!=='look')return
    for(const look of looks)post({type:'render',key:`look:${look.id}`,target:'preview',settings:fittedLooks[look.id],browWeight:browImages&&!browFill&&brows.on?Math.min(1,brows.amount/.3):0,browFill:ownBrowPreview})
  },[previewFace,mode,looks,fittedLooks,browImages,browFill,brows.on,brows.amount,ownBrowPreview,post])
  const mainFrame=frames.main&&face&&frames.main.token===face.token?frames.main:null
  useEffect(()=>{
    if(!loaded||!crop||!canvas.current)return
    const el=canvas.current;el.width=loaded.image.width;el.height=loaded.image.height
    const ctx=el.getContext('2d');if(!ctx)return
    ctx.putImageData(loaded.image,0,0)
    if(holding||!mainFrame||!face)return
    ctx.putImageData(new ImageData(new Uint8ClampedArray(mainFrame.data),mainFrame.width,mainFrame.height),crop.x0,crop.y0)
    ctx.save();ctx.translate(crop.x0,crop.y0)
    if(browImages)drawBrows(ctx,face,browImages,{...brows,amount:Math.min(1,brows.amount*scale)},browFill)
    drawLashes(ctx,face,lashCatalog,lashImages,{...renderLashes,amount:Math.min(1,renderLashes.amount*scale)})
    ctx.restore()
  },[loaded,crop,mainFrame,face,holding,browImages,brows,scale,lashCatalog,lashImages,renderLashes,browFill])
  function pickOccasion(next:MakeupOccasion){setBrowTouched(false);setAssetId(null);setLashAmount(null);setLowerAmount(null);setOccasion(next);setSelectedId(recommendMakeupLooks({...profile,faceShape,lipPale},next)[0].id);setIntensity(1);setAmounts(INITIAL_AMOUNTS)}
  function pickLook(id:LookId){setBrowTouched(false);setAssetId(null);setLashAmount(null);setLowerAmount(null);setSelectedId(id);setIntensity(1);setAmounts(INITIAL_AMOUNTS)}
  // 묶음 강도: 묶음 안 부위를 같은 값으로, 눈 묶음은 속눈썹도 같이
  function setGroup(id:(typeof GROUPS)[number]['id'],value:number){
    const group=GROUPS.find(item=>item.id===id)!
    setAmounts(current=>({...current,...Object.fromEntries(group.parts.map(part=>[part,value]))}))
    if(id==='eye'){setLashAmount(Math.min(1,Math.round(DEFAULT_LASHES.amount*eyeFit*value*100)/100));setLowerAmount(Math.min(1,Math.round(DEFAULT_LASHES.lower*eyeFit*value*100)/100))}
  }
  function save(){const link=document.createElement('a');link.download=`boa-${mode==='custom'?'custom':selectedId}.png`;link.href=canvas.current?.toDataURL('image/png')??'';link.click()}
  const ready=Boolean(face)
  const shown=Boolean(mainFrame)
  function customControl(part:Exclude<MakeupPart,'skin'>) {
    const layer=custom[part],shapes=MAKEUP_SHAPES[part] as {id:string;label:string;description:string}[],off=!ready||!layer.on
    return <details key={part} className="makeup-foldout makeup-custom-part" open={layer.on||undefined}>
      <summary><label className="makeup-toggle" onClick={e=>e.stopPropagation()}><input type="checkbox" checked={layer.on} disabled={!ready} onChange={e=>updateCustom(part,{on:e.target.checked})}/>{PART_LABELS[part]}</label>{layer.on&&<span className="makeup-custom-chip" style={{background:layer.hex}}/>}</summary>
      {shapes.length>1&&<div className="category-filters makeup-liner-options" role="group" aria-label={`${PART_LABELS[part]} 종류`}>{shapes.map(item=><button key={item.id} type="button" title={item.description} aria-pressed={layer.shape===item.id} disabled={off} onClick={()=>updateCustom(part,{shape:item.id} as Partial<MakeupSettings[typeof part]>)}>{item.label}</button>)}</div>}
      <div className="makeup-swatches" role="group" aria-label={`${PART_LABELS[part]} 색`}>{swatches[part].map(hex=><button key={hex} type="button" title={hex} aria-pressed={layer.hex===hex} disabled={off} style={{background:hex}} onClick={()=>updateCustom(part,{hex})}/>)}<label className="makeup-swatch-picker"><ColorPick value={layer.hex} disabled={off} label={`${PART_LABELS[part]} 색 직접 고르기`} onPick={hex=>updateCustom(part,{hex})}/></label></div>
      <label className="makeup-amount">강도<input type="range" min="0" max="1" step="0.05" value={layer.amount} disabled={off} onChange={e=>updateCustom(part,{amount:Number(e.target.value)})}/><span>{Math.round(layer.amount*100)}%</span></label>
      {part==='blush'&&<label className="makeup-amount">광<input type="range" min="0" max="1" step="0.05" value={layer.glow??0} disabled={off} onChange={e=>updateCustom('blush',{glow:Number(e.target.value)})}/><span>{Math.round((layer.glow??0)*100)}%</span></label>}
      {part==='lip'&&<label className="makeup-amount">윤기<input type="range" min="0" max="1" step="0.05" value={layer.gloss??0} disabled={off} onChange={e=>updateCustom('lip',{gloss:Number(e.target.value)})}/><span>{Math.round((layer.gloss??0)*100)}%</span></label>}
    </details>
  }
  return <section className="form-card makeup-workspace">
    <div className="makeup-result" role="region" aria-label="메이크업 결과">
      <div className="makeup-result-heading"><div className="card-heading"><span className="step-number">03</span><div><h3 id="makeup-result-title" className="section-target" tabIndex={-1}>{file?(mode==='custom'?'직접 꾸미기':selected.name):'메이크업 미리보기'}</h3><p>메이크업과 강도를 바꾸면 바로 반영돼요.</p></div></div>{file&&<span className="category-pill">{occasionInfo.label}</span>}</div>
      <div className="makeup-result-stage" aria-busy={Boolean(file&&!shown&&!error)}>
        {error||workerError?<p role="alert" className="error-box">{error||workerError}</p>:!file?<div className="makeup-result-empty"><strong>사진을 등록해 주세요</strong><p>01에서 사진을 올리면<br/>이곳에서 결과를 바로 볼 수 있어요.</p></div>:!shown?<p role="status" className="color-studio-loading"><span className="spinner"/>얼굴과 눈 영역을 준비하고 있어요…</p>:null}
        <canvas ref={canvas} hidden={!shown||Boolean(error||workerError)} aria-label={`${mode==='custom'?'직접 꾸미기':selected.name} 메이크업 결과`}/>
      </div>
      <div className="color-studio-actions">
        <button type="button" className="secondary" disabled={!ready} onPointerDown={()=>setHolding(true)} onPointerUp={()=>setHolding(false)} onPointerLeave={()=>setHolding(false)} onPointerCancel={()=>setHolding(false)} onKeyDown={e=>{if(e.key===' '||e.key==='Enter'){e.preventDefault();setHolding(true)}}} onKeyUp={()=>setHolding(false)} onBlur={()=>setHolding(false)}>누르는 동안 원본 보기</button>
        <button type="button" onClick={save} disabled={!ready}>이미지 저장</button>
      </div>
    </div>
    <aside className="makeup-editor makeup-controls" aria-label="메이크업 설정">
      <div className="category-filters makeup-part-tabs makeup-mode-tabs" role="tablist" aria-label="메이크업 방식">{([['look','추천 메이크업'],['custom','직접 꾸미기']] as const).map(([id,label])=><button key={id} type="button" role="tab" aria-selected={mode===id} aria-pressed={mode===id} onClick={()=>setMode(id)}>{label}</button>)}</div>
      {mode==='look'?<>
      <div className="makeup-editor-overview"><div className="card-heading"><div><h3>추천 메이크업</h3><p>얼굴형·코·광대 분석에 맞춰 위치를 잡아요. 강도만 조절할 수 있어요.</p></div></div>
        {fit&&<ul className="makeup-fit-summary" aria-label="내 얼굴 맞춤">{fitSummary(fit,faceShape).map(line=><li key={line}>{line}</li>)}</ul>}</div>
          <fieldset className="makeup-occasion"><legend>오늘의 상황</legend><div className="category-filters makeup-occasion-options" role="group" aria-label="메이크업 상황 선택">{occasions.map(item=><button type="button" key={item.id} aria-pressed={occasion===item.id} onClick={()=>pickOccasion(item.id)}>{item.label}</button>)}</div><p aria-live="polite">{occasionInfo.description} · 추천 메이크업 {looks.length}개</p></fieldset>
          <div className="makeup-look-grid" role="group" aria-label="추천 메이크업">{looks.map(look=><button type="button" key={look.id} className="makeup-look-card" aria-pressed={selected.id===look.id} onClick={()=>pickLook(look.id)}>
            <LookPreview browFill={browFill} frame={frames[`look:${look.id}`]} face={previewFace} browImages={browImages} brows={brows} lash={previewLash[look.lashes]??previewLash.none}/><span className="eyebrow">{look.mood}</span><strong>{look.name}</strong><span>{look.description}</span><span className="makeup-look-colors">{(['eyeshadow','shadowPoint','underShadow','blush','lip'] as const).filter(part=>look.settings[part].on).map(part=><span key={part} title={`${PART_LABELS[part]} ${look.settings[part].hex}`} style={{background:look.settings[part].hex}}/>)}</span>
          </button>)}</div>
      <section className="makeup-strengths" aria-label="메이크업 강도 조절">
        <div className="makeup-strengths-heading"><h3>강도 조절</h3><button type="button" className="secondary" onClick={()=>pickLook(selected.id)}>기본값으로</button></div>
        <p className="makeup-panel-note">0%로 내리면 해당 효과가 꺼져요. 모양·색은 직접 꾸미기에서 바꿀 수 있어요.</p>
        <div className="makeup-look-intensity"><label className="makeup-amount">전체 강도<input type="range" min="0" max="1.5" step="0.05" value={intensity} disabled={!ready} onChange={e=>setIntensity(Number(e.target.value))}/><span>{Math.round(intensity*100)}%</span></label></div>
        {GROUPS.filter(group=>group.parts.some(part=>selected.settings[part].on)).map(group=>{const value=amounts[group.parts.find(part=>selected.settings[part].on)!]
          return <label key={group.id} className="makeup-amount">{group.label}<input type="range" min="0" max="1.5" step="0.05" value={value} disabled={!ready} onChange={e=>setGroup(group.id,Number(e.target.value))}/><span>{Math.round(value*100)}%</span></label>})}
        <label className="makeup-toggle"><input type="checkbox" checked={brows.on} disabled={!ready} onChange={e=>updateBrows(current=>({...current,on:e.target.checked}))}/>{browFill?'눈썹 빈 곳 채우기':ownFill?'내 눈썹 빈 곳 채우기':'눈썹 정리'}</label>
        {brows.on&&<label className="makeup-amount">눈썹 농도<input type="range" min="0" max="1" step="0.05" value={brows.amount} disabled={!ready} onChange={e=>setBrowAmount(Number(e.target.value))}/><span>{Math.round(brows.amount*100)}%</span></label>}
      </section>
      </>:<>
      <section className="makeup-strengths makeup-custom" aria-label="직접 꾸미기">
        <div className="makeup-strengths-heading"><h3>직접 꾸미기</h3><button type="button" className="secondary" onClick={()=>{setCustom(null);setCustomLash(null)}}>맨얼굴로</button></div>
        <p className="makeup-panel-note">맨얼굴에서 시작해요. 부위를 켜고 종류·색·강도를 골라 보세요.</p>
        <label className="makeup-amount">피부 보정<input type="range" min="0" max="1" step="0.05" value={custom.skin.on?custom.skin.amount:0} disabled={!ready} onChange={e=>updateCustom('skin',{on:Number(e.target.value)>0,amount:Number(e.target.value)})}/><span>{Math.round((custom.skin.on?custom.skin.amount:0)*100)}%</span></label>
        {CUSTOM_ORDER.map(customControl)}
        {/* 남성은 속눈썹 없음 */}
        {profile.sex!=='male'&&<details className="makeup-foldout makeup-custom-part" open={customLashes.style!=='none'||undefined}><summary>속눈썹 <span>{customLashes.style==='none'?'없음':lashCatalog.find(a=>a.id===customLashes.style)?.label}</span></summary>
          {lashCatalog.length===0&&<p className="makeup-panel-note">속눈썹 모양을 불러오는 중이에요…</p>}
          <div className="category-filters makeup-liner-options" role="group" aria-label="속눈썹 모양">{[{id:'none',label:'없음'},...lashCatalog].map(item=><button key={item.id} type="button" aria-pressed={customLashes.style===item.id} disabled={!ready} onClick={()=>setCustomLash({...customLashes,style:item.id})}>{item.label}</button>)}</div>
          <label className="makeup-amount">강도<input type="range" min="0" max="1" step="0.05" value={customLashes.amount} disabled={!ready||customLashes.style==='none'} onChange={e=>setCustomLash({...customLashes,amount:Number(e.target.value)})}/><span>{Math.round(customLashes.amount*100)}%</span></label>
          {lashCatalog.find(a=>a.id===customLashes.style)?.lower&&<label className="makeup-amount">아래 속눈썹<input type="range" min="0" max="1" step="0.05" value={customLashes.lower} disabled={!ready} onChange={e=>setCustomLash({...customLashes,lower:Number(e.target.value)})}/><span>{Math.round(customLashes.lower*100)}%</span></label>}
        </details>}
      <details className="makeup-foldout makeup-custom-part makeup-brow-settings"><summary>눈썹 <span>{brows.on?'적용 중':'선택 안 함'}</span></summary>
        <section className="makeup-brows"><h3>눈썹 모양 <span>{styles.length}종</span></h3><p>{browFill?'원래 눈썹은 그대로 두고 고른 모양 안의 빈 곳만 채워요.':ownFill?'지금은 내 눈썹 모양 그대로 빈 곳만 채우고 있어요. 모양을 고르면 그 모양으로 바꿔요.':'인식한 눈썹 중심에 맞춰요. 너비와 두께를 각각 조절할 수 있어요.'}</p>
          {browError&&<p role="alert" className="error-box">{browError}</p>}
          <fieldset disabled={!ready}>
            <legend><label className="makeup-toggle"><input type="checkbox" checked={brows.on} onChange={e=>updateBrows(current=>({...current,on:e.target.checked}))}/>눈썹 적용</label></legend>
            <div className="makeup-brow-grid" role="group" aria-label="눈썹 모양 선택">{styles.map(style=><button type="button" key={style.id} aria-pressed={brows.on&&!ownFill&&assetId===style.id} onClick={()=>{setAssetId(style.id);updateBrows(current=>({...current,on:true,width:style.width,thickness:style.thickness,vertical:DEFAULT_BROWS.vertical,spread:DEFAULT_BROWS.spread}))}}><span className="makeup-brow-thumb"><img src={style.asset.preview} alt=""/></span><span>{style.label}</span><small>{style.asset.group}</small></button>)}</div>
            {brows.on&&!ownFill&&!browImages&&!browError&&<p role="status">눈썹을 불러오는 중…</p>}
            <label className="makeup-amount">농도<input type="range" min="0" max="1" step="0.05" value={brows.amount} onChange={e=>setBrowAmount(Number(e.target.value))}/><span>{Math.round(brows.amount*100)}%</span></label>
            <label className="makeup-brow-color">눈썹 색<ColorPick value={brows.hex} label="눈썹 색" onPick={setBrowHex}/></label>
            {!ownFill&&<div>{([{key:'width',label:'너비',min:.5,max:2,step:.05},{key:'thickness',label:'두께',min:.5,max:2,step:.05},{key:'vertical',label:'상하 위치',min:-5,max:5,step:.25},{key:'spread',label:'좌우 간격',min:-4,max:4,step:.25}] as const).map(control=><label key={control.key} className="makeup-amount">{control.label}<input type="range" min={control.min} max={control.max} step={control.step} value={brows[control.key]} onChange={e=>updateBrows(current=>({...current,[control.key]:Number(e.target.value)}))}/><span>{brows[control.key].toFixed(2)}</span></label>)}</div>}
            <button type="button" className="secondary" onClick={()=>{setAssetId(null);setBrows(INITIAL_BROWS);setBrowTouched(profile.sex!=='female');setOwnAmount(OWN_BROW_AMOUNT);setBrowHex(null)}}>눈썹 초기화</button>
          </fieldset>
        </section>
      </details>
      </section>
      </>}
    </aside>
  </section>
}
