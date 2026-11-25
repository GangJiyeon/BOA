import { hairImageUrl } from '../api/hair-image'
import { useEffect, useState, type Ref } from 'react'
import { createHairRender, getHairRender, type HairRender } from '../api/studio'
import { getHairStyles, type HairStyle } from '../api/hair'
import PageIntro, { ProgressSteps } from '../components/PageIntro'
import PhotoPreview from '../components/PhotoPreview'
import Icon from '../components/Icon'
import PhotoUpload from '../components/PhotoUpload'
import { TaskStatus } from '../components/Shared'
import HairColorStudio from '../components/HairColorStudio'
import { useTask } from '../hooks/useTask'
import { measureSkinTone, type SkinToneResult } from '../api/skin'
import { recommendHairColors, type HairColorRecommendation } from '../studio/hairColorRecommendations'
import type { HairSessionResult, StudioMakeupResult } from '../types/sessionResults'
import { useAdoptSessionPhoto, type SessionPhotoProps } from '../hooks/useSessionPhoto'
import './StudioPage.css'

const POLL_MS = 2000
const POLL_LIMIT = 90
const labels: Record<string,string> = {female:'여성',male:'남성',unisex:'공용',short:'짧게',medium:'중간',long:'길게',straight:'직모',wavy:'웨이브',curly:'컬'}
// 서버가 단계를 알려주지 않아 지난 시간으로 안내 (AI 생성 약 1분 + 얼굴 맞춤 합성 약 15초)
const STAGES:[number,string,string][]=[
  [0,'사진을 인식하고 있어요','얼굴 각도와 크기를 살펴보고 있어요.'],
  [5,'AI가 머리를 합성하고 있어요','선택한 헤어스타일을 사진에 입히고 있어요.'],
  [60,'내 얼굴에 맞춰 다듬고 있어요','얼굴은 그대로 두고 새 머리만 자연스럽게 입히고 있어요.'],
  [90,'거의 다 됐어요','조금만 더 기다려 주세요.'],
]
const STEP_LABELS=['사진 인식','AI 머리 합성','얼굴 맞춤','마무리']
type WaitStyle={name:string;image:string|null;guide:string|null;tags:string[];fits:string[];myFit:[string,number]|null}
// 카탈로그 안내 형식 "설명 (무드: a, b / 시술·스타일링: c, d)" → 설명 + 그룹별 태그, 형식이 다르면 통째로 설명
function parseGuide(text:string|null|undefined){
  if(!text)return{desc:'',groups:[] as [string,string[]][]}
  const m=text.match(/^(.*?)\s*\(([^()]*)\)\s*$/)
  if(!m)return{desc:text,groups:[]}
  const groups=m[2].split('/').map(part=>{
    const i=part.indexOf(':')
    return i<0?null:[part.slice(0,i).trim(),part.slice(i+1).split(',').map(t=>t.trim()).filter(Boolean)] as [string,string[]]
  }).filter((g):g is [string,string[]]=>!!g&&g[1].length>0)
  return{desc:m[1],groups}
}
function StudioProgress({style}:{style?:WaitStyle}) {
  const [sec,setSec]=useState(0)
  useEffect(()=>{
    const start=Date.now(),id=setInterval(()=>setSec(Math.floor((Date.now()-start)/1000)),1000)
    return()=>clearInterval(id)
  },[])
  const step=STAGES.filter(([at])=>sec>=at).length-1
  const [,title,note]=STAGES[step]
  const {desc,groups}=parseGuide(style?.guide)
  return <section className="studio-wait" aria-busy="true">
    <div className="request-progress"><span className="spinner"/><div>
      <strong role="status">{title}</strong>
      <p>{note}</p>
    </div></div>
    <ol className="studio-wait-steps" aria-label="합성 단계">{STEP_LABELS.map((label,i)=><li key={label} className={i<step?'done':i===step?'current':undefined} aria-current={i===step?'step':undefined}><span>{i<step?'✓':i+1}</span>{label}</li>)}</ol>
    {style&&<div className="studio-wait-style">
      {style.image?<img src={hairImageUrl(style.image)} alt=""/>:<span className="image-placeholder"/>}
      <div>
        <h4>{style.name}</h4>
        {style.tags.length>0&&<p className="studio-wait-meta">{style.tags.join(' · ')}</p>}
        {desc&&<p className="studio-wait-desc">{desc}</p>}
        {groups.map(([label,items])=><div key={label} className="studio-wait-tags"><small>{label}</small>{items.map(item=><span key={item} className="category-pill">{item}</span>)}</div>)}
        {style.fits.length>0&&<div className="studio-wait-tags"><small>잘 어울리는 얼굴형</small>{style.fits.map(item=><span key={item} className="category-pill">{item}</span>)}</div>}
        {style.myFit&&<p className="studio-wait-fit">내 얼굴형({style.myFit[0]}) 적합도 <strong>{Math.round(style.myFit[1]*100)}%</strong></p>}
      </div>
    </div>}
  </section>
}
function wait(ms:number,signal:AbortSignal) {
  return new Promise<void>((resolve,reject)=>{
    if(signal.aborted){reject(new DOMException('aborted','AbortError'));return}
    const abort=()=>{clearTimeout(id);reject(new DOMException('aborted','AbortError'))}
    const id=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve()},ms)
    signal.addEventListener('abort',abort,{once:true})
  })
}

// 얼굴형 적합도 이 이상이면 '잘 어울리는 얼굴형'으로 표시 (최대 3개)
const GOOD_FIT=0.85
function waitStyle(item:HairStyle|HairSessionResult['result']['recommendations'][number],info:HairStyle|undefined,faceShape:string|null):WaitStyle{
  const fit=info?.face_fit??{}
  const tags=[...('rank' in item?[`추천 ${item.rank}위`]:[]),...(info?[labels[info.sex]??info.sex,labels[info.length]??info.length,labels[info.texture]??info.texture]:[])]
  return{
    name:item.name,image:item.image,
    guide:'rank' in item?item.note:item.guide??null,
    tags,
    fits:Object.entries(fit).filter(([,v])=>v>=GOOD_FIT).sort((a,b)=>b[1]-a[1]).slice(0,3).map(([k])=>k),
    myFit:faceShape&&fit[faceShape]!=null?[faceShape,fit[faceShape]]:null,
  }
}

export default function StudioPage({hair,onUsed,onMakeup,makeupExport,sessionPhoto,onPhoto}:SessionPhotoProps&{hair:HairSessionResult|null;onUsed:()=>void;onMakeup:(result:StudioMakeupResult)=>void;makeupExport?:Ref<()=>boolean>}) {
  const task=useTask()
  // 사진 출처(헤어 추천 사진·직접 업로드)와 스타일 목록(추천·전체)은 따로 고름
  const [mode,setMode]=useState<'catalog'|'recommendation'>(hair?'recommendation':'catalog')
  const activeMode=mode==='recommendation'&&hair?'recommendation':'catalog'
  const [styleTab,setStyleTab]=useState<'recommended'|'all'>(hair?'recommended':'all')
  const activeTab=styleTab==='recommended'&&hair?'recommended':'all'
  const [photos,setPhotos]=useState<File[]>([])
  useAdoptSessionPhoto(sessionPhoto,photos.length===0&&!task.busy,file=>{if(file.size<=10*1024*1024)setPhotos([file])})
  const [photoError,setPhotoError]=useState('')
  const [styles,setStyles]=useState<HairStyle[]>([])
  const [loading,setLoading]=useState(true)
  const [catalogError,setCatalogError]=useState('')
  const [revision,setRevision]=useState(0)
  const [catalogId,setCatalogId]=useState('')
  const [recommendedId,setRecommendedId]=useState(hair?.result.recommendations[0]?.style_id??'')
  // 전체 목록 구분 필터는 헤어 분석 때 고른 성별로 시작
  const [sex,setSex]=useState<string>(hair?.analysis.sex??''),[length,setLength]=useState(''),[texture,setTexture]=useState('')
  const [render,setRender]=useState<{value:HairRender;styleName:string;photo:File}|null>(null)
  // 스튜디오를 먼저 열어 둔 뒤 새 헤어 추천이 오면 추천 모드로 전환 (헤어색만 추가된 갱신은 run_id 같아서 유지, 합성 중엔 유지)
  const runId=hair?.result.run_id??null
  const [seenRunId,setSeenRunId]=useState(runId)
  if(runId!==seenRunId){
    setSeenRunId(runId)
    if(runId!==null&&!task.busy){setMode('recommendation');setStyleTab('recommended');setSex(hair!.analysis.sex);setRecommendedId(hair!.result.recommendations[0]?.style_id??'');setRender(null)}
  }
  // 추천 헤어색: 헤어 페이지에서 같은 사진으로 받아둔 게 있으면 그대로, 없으면 합성 사진으로 피부톤 분석 (실패하면 추천 없이)
  const [toneRecs,setToneRecs]=useState<{photo:File;colors:HairColorRecommendation[];basis:string;skinTone?:SkinToneResult}|null>(null)
  const sessionRecs=render&&hair?.recommendedColors&&render.photo===hair.photo?{colors:hair.recommendedColors,basis:hair.hairColorBasis,skinTone:hair.skinTone}:null
  const colorRecs=sessionRecs??(render&&toneRecs?.photo===render.photo?toneRecs:null)
  const needTone=render&&!sessionRecs&&toneRecs?.photo!==render.photo?render.photo:null
  useEffect(()=>{
    if(!needTone)return
    const controller=new AbortController()
    measureSkinTone(needTone,controller.signal).then(sample=>{
      if(controller.signal.aborted)return
      const {colors,basis}=recommendHairColors(sample)
      setToneRecs({photo:needTone,colors,basis,skinTone:sample})
    }).catch(()=>{if(!controller.signal.aborted)setToneRecs({photo:needTone,colors:[],basis:''})})
    return()=>controller.abort()
  },[needTone])
  useEffect(()=>{
    // 추천 목록도 대기 화면 설명(길이·질감·얼굴형 적합도)용으로 카탈로그 조회
    const controller=new AbortController()
    setLoading(true);setCatalogError('')
    getHairStyles(controller.signal).then(value=>{
      if(!controller.signal.aborted){setStyles(value);setLoading(false)}
    }).catch(error=>{
      if(!controller.signal.aborted){setCatalogError(error instanceof Error?error.message:'카탈로그 조회 실패');setLoading(false)}
    })
    return()=>controller.abort()
  },[revision])
  const recs=hair?.result.recommendations??[]
  const visible=styles.filter(item=>(!sex||item.sex===sex||item.sex==='unisex')&&(!length||item.length===length)&&(!texture||item.texture===texture))
  const rankOf=new Map(recs.map(item=>[item.style_id,item.rank]))
  const selected=activeTab==='recommended'?(recs.find(item=>item.style_id===recommendedId)??recs[0]):visible.find(item=>item.style_id===catalogId)
  const photo=activeMode==='recommendation'?hair?.photo:photos[0]
  const ready=!!photo&&!!selected&&!task.busy&&(activeTab==='recommended'||(!loading&&!catalogError))&&(activeMode==='recommendation'||!photoError)
  function clearResult(){task.reset();setRender(null)}
  function changeMode(next:'catalog'|'recommendation'){
    if(task.busy||next===activeMode)return
    clearResult();setMode(next)
  }
  function changeTab(next:'recommended'|'all'){
    if(task.busy||next===activeTab)return
    setStyleTab(next)
  }
  function selectPhotos(files:File[]){
    if(task.busy)return
    clearResult()
    if(files.some(file=>file.size>10*1024*1024)){setPhotoError('사진은 10MB 이하로 올려 주세요.');return}
    setPhotoError('');setPhotos(files);onPhoto?.(files[0]??null,photos[0]??null)
  }
  function changeFilter(update:(value:string)=>void,value:string){clearResult();update(value);setCatalogId('')}
  function start(){
    if(!ready||!photo||!selected)return
    const submittedPhoto=photo,style=selected,runId=hair&&rankOf.has(style.style_id)?hair.result.run_id:null
    setRender(null)
    void task.run(async signal=>{
      let value=await createHairRender(submittedPhoto,style.style_id,runId,signal)
      if(signal.aborted)return
      onUsed()
      for(let i=0;value.status==='pending';i++){
        if(i>=POLL_LIMIT)throw new Error('합성이 오래 걸리고 있어요. 잠시 후 다시 시도해 주세요.')
        await wait(POLL_MS,signal)
        value=await getHairRender(value.id,signal)
      }
      if(signal.aborted)return
      if(value.status==='failed'){onUsed();throw new Error(value.error??'합성에 실패했습니다.')}
      setRender({value,styleName:style.name,photo:submittedPhoto})
    })
  }
  // 얼굴형·헤어 추천 페이지와 같은 흐름: 01 사진 · 02 스타일 고르고 합성하기 → 03 결과
  return <section><PageIntro eyebrow="AI STUDIO" title="AI 헤어 스튜디오">사진과 스타일을 골라 합성하고, 32가지 머리색을 바꿔 보세요.</PageIntro>
    <ProgressSteps labels={['사진 입력','스타일 선택','AI 합성']} current={render?3:task.busy?2:photo?1:0}/>
    <div className="analysis-layout studio-layout">
      <section className="form-card input-panel">
        <div className="card-heading"><span className="step-number">01</span><div><h3>합성할 사진</h3><p>정면 얼굴 사진 1장 · 최대 10MB</p></div></div>
        <div className="studio-entry"><div className="button-row" role="group" aria-label="스튜디오 시작 방법">
          <button type="button" aria-pressed={activeMode==='catalog'} disabled={task.busy} onClick={()=>changeMode('catalog')}>사진 업로드 · 직접 선택</button>
          <button type="button" aria-pressed={activeMode==='recommendation'} disabled={task.busy||!hair} onClick={()=>changeMode('recommendation')}>헤어 추천에서 가져오기</button>
        </div></div>
        {activeMode==='catalog'?<>
          <PhotoUpload files={photos} onChange={selectPhotos} disabled={task.busy}/>
          {photoError&&<p role="alert" className="error-box">{photoError}</p>}
          {!hair&&<p className="input-note">헤어 추천 결과도 사용할 수 있어요. <a href="#/hair">얼굴형 · 헤어 추천 받기</a></p>}
        </>:<>
          <p className="input-note">얼굴형 분석({hair!.analysis.face_shape})에 사용한 정면 사진이에요.</p>
          <div className="studio-hair-photo"><PhotoPreview file={hair!.photo}/></div>
        </>}
      </section>
      <section className="form-card options-panel studio-options">
        <div className="card-heading"><span className="step-number">02</span><div><h3>스타일 선택</h3><p>입어 보고 싶은 스타일을 골라 주세요.</p></div></div>
        {hair&&<div className="studio-entry"><div className="button-row" role="group" aria-label="스타일 목록">
          <button type="button" aria-pressed={activeTab==='recommended'} disabled={task.busy} onClick={()=>changeTab('recommended')}>추천 스타일</button>
          <button type="button" aria-pressed={activeTab==='all'} disabled={task.busy} onClick={()=>changeTab('all')}>전체 스타일</button>
        </div></div>}
        {activeTab==='all'&&<>
          <fieldset className="studio-catalog-filters" disabled={task.busy||loading}><legend className="sr-only">카탈로그 필터</legend>
            <label className="field">스타일 구분<select value={sex} onChange={e=>changeFilter(setSex,e.target.value)}><option value="">전체</option>{['female','male','unisex'].map(value=><option key={value} value={value}>{labels[value]}</option>)}</select></label>
            <label className="field">길이<select value={length} onChange={e=>changeFilter(setLength,e.target.value)}><option value="">전체</option>{[...new Set(styles.map(item=>item.length))].map(value=><option key={value} value={value}>{labels[value]??value}</option>)}</select></label>
            <label className="field">질감<select value={texture} onChange={e=>changeFilter(setTexture,e.target.value)}><option value="">전체</option>{[...new Set(styles.map(item=>item.texture))].map(value=><option key={value} value={value}>{labels[value]??value}</option>)}</select></label>
          </fieldset>
          {loading&&<p role="status">스타일 카탈로그를 불러오는 중…</p>}
          {catalogError&&<p role="alert" className="error-box">카탈로그 조회 실패: {catalogError} <button type="button" onClick={()=>setRevision(value=>value+1)}>다시 조회</button></p>}
          {!loading&&!catalogError&&!visible.length&&<p className="empty-box">{styles.length?'선택한 조건에 맞는 스타일이 없습니다. 필터를 바꿔 주세요.':'등록된 헤어스타일이 없습니다.'}</p>}
        </>}
        <fieldset className="studio-styles" disabled={task.busy||(activeTab==='all'&&(loading||!!catalogError))}><legend className="sr-only">합성할 헤어스타일</legend>
          {(activeTab==='recommended'?recs:visible).map(item=><label key={item.style_id} className={`studio-style${item.style_id===selected?.style_id?' selected':''}`}>
            <input type="radio" name="studio-style" value={item.style_id} checked={item.style_id===selected?.style_id} onChange={()=>{clearResult();if(activeTab==='recommended')setRecommendedId(item.style_id);else setCatalogId(item.style_id)}}/>
            {item.image?<img src={hairImageUrl(item.image)} alt="" loading="lazy"/>:<span className="image-placeholder"/>}
            <span><small>{'rank' in item?`추천 ${item.rank}`:`${rankOf.has(item.style_id)?`추천 ${rankOf.get(item.style_id)} · `:''}${labels[item.sex]??item.sex} · ${labels[item.length]??item.length}`}</small>{item.name}</span>
          </label>)}
        </fieldset>
        {activeTab==='recommended'&&!recs.length&&<p className="empty-box">추천 스타일이 없습니다. 전체 스타일에서 골라 주세요.</p>}
        {selected&&<p className="input-note studio-selected">선택한 스타일: <strong>{selected.name}</strong></p>}
        <button className="recommend-button" type="button" disabled={!ready} onClick={start}>{task.busy?'합성하고 있어요…':'AI로 헤어 합성하기'}<Icon name="arrow" size={18}/></button>
        <p className="input-note">사진은 합성을 위해 Google AI로 전송됩니다. 비회원은 하루 이용 횟수가 정해져 있어요.</p>
      </section>
    </div>
    {task.busy&&<StudioProgress style={selected&&waitStyle(selected,styles.find(item=>item.style_id===selected.style_id),activeMode==='recommendation'&&hair?hair.analysis.face_shape:null)}/>}
    <TaskStatus busy={false} error={task.error}/>
    {render&&<section className="form-card studio-result"><div className="card-heading"><span className="step-number">03</span><div><h3>머리색 바꿔보기</h3><p>{render.styleName} · 색을 누르면 바로 바뀌어요.</p></div></div><HairColorStudio key={render.value.id} render={render.value} styleName={render.styleName} recommendedColors={colorRecs?.colors} basis={colorRecs?.basis} skinTone={colorRecs?.skinTone}
      makeupExport={makeupExport} onMakeup={photo=>onMakeup({photo,sourcePhoto:render.photo,styleName:render.styleName})}/></section>}
  </section>
}
