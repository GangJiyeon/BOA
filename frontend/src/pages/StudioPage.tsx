import { useEffect, useState } from 'react'
import { createHairRender, getHairRender, type HairRender } from '../api/studio'
import { getHairStyles, type HairStyle } from '../api/hair'
import PageIntro from '../components/PageIntro'
import Icon from '../components/Icon'
import PhotoUpload from '../components/PhotoUpload'
import { TaskStatus } from '../components/Shared'
import HairColorStudio from '../components/HairColorStudio'
import { useTask } from '../hooks/useTask'
import type { HairSessionResult } from '../types/sessionResults'
import './StudioPage.css'

const POLL_MS = 2000
const POLL_LIMIT = 90
const labels: Record<string,string> = {female:'여성',male:'남성',unisex:'공용',short:'짧게',medium:'중간',long:'길게',straight:'직모',wavy:'웨이브',curly:'컬'}
function wait(ms:number,signal:AbortSignal) {
  return new Promise<void>((resolve,reject)=>{
    if(signal.aborted){reject(new DOMException('aborted','AbortError'));return}
    const abort=()=>{clearTimeout(id);reject(new DOMException('aborted','AbortError'))}
    const id=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve()},ms)
    signal.addEventListener('abort',abort,{once:true})
  })
}

export default function StudioPage({hair,onUsed}:{hair:HairSessionResult|null;onUsed:()=>void}) {
  const task=useTask()
  const [mode,setMode]=useState<'catalog'|'recommendation'>(hair?'recommendation':'catalog')
  const activeMode=mode==='recommendation'&&hair?'recommendation':'catalog'
  const [photos,setPhotos]=useState<File[]>([])
  const [photoError,setPhotoError]=useState('')
  const [styles,setStyles]=useState<HairStyle[]>([])
  const [loading,setLoading]=useState(true)
  const [catalogError,setCatalogError]=useState('')
  const [revision,setRevision]=useState(0)
  const [catalogId,setCatalogId]=useState('')
  const [recommendedId,setRecommendedId]=useState(hair?.result.recommendations[0]?.style_id??'')
  const [sex,setSex]=useState(''),[length,setLength]=useState(''),[texture,setTexture]=useState('')
  const [render,setRender]=useState<{value:HairRender;styleName:string}|null>(null)
  useEffect(()=>{
    if(activeMode!=='catalog')return
    const controller=new AbortController()
    setLoading(true);setCatalogError('')
    getHairStyles(controller.signal).then(value=>{
      if(!controller.signal.aborted){setStyles(value);setLoading(false)}
    }).catch(error=>{
      if(!controller.signal.aborted){setCatalogError(error instanceof Error?error.message:'카탈로그 조회 실패');setLoading(false)}
    })
    return()=>controller.abort()
  },[activeMode,revision])
  const recs=hair?.result.recommendations??[]
  const visible=styles.filter(item=>(!sex||item.sex===sex||item.sex==='unisex')&&(!length||item.length===length)&&(!texture||item.texture===texture))
  const selected=activeMode==='recommendation'?(recs.find(item=>item.style_id===recommendedId)??recs[0]):visible.find(item=>item.style_id===catalogId)
  const photo=activeMode==='recommendation'?hair?.photo:photos[0]
  const ready=!!photo&&!!selected&&!task.busy&&(activeMode==='recommendation'||(!loading&&!catalogError&&!photoError))
  function clearResult(){task.reset();setRender(null)}
  function changeMode(next:'catalog'|'recommendation'){
    if(task.busy||next===activeMode)return
    clearResult();setMode(next)
  }
  function selectPhotos(files:File[]){
    if(task.busy)return
    clearResult()
    if(files.some(file=>file.size>10*1024*1024)){setPhotoError('사진은 10MB 이하로 올려 주세요.');return}
    setPhotoError('');setPhotos(files)
  }
  function changeFilter(update:(value:string)=>void,value:string){clearResult();update(value);setCatalogId('')}
  function start(){
    if(!ready||!photo||!selected)return
    const submittedPhoto=photo,style=selected,runId=activeMode==='recommendation'?hair!.result.run_id:null
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
      if(value.status==='failed')throw new Error(value.error??'합성에 실패했습니다.')
      setRender({value,styleName:style.name})
    })
  }
  return <section><PageIntro eyebrow="AI STUDIO" title="AI 헤어 스튜디오">사진과 스타일을 골라 합성하고, 32가지 머리색을 바꿔 보세요.</PageIntro>
    <section className="form-card studio-entry">
      <h3>시작 방법</h3><div className="button-row" role="group" aria-label="스튜디오 시작 방법">
        <button type="button" aria-pressed={activeMode==='catalog'} disabled={task.busy} onClick={()=>changeMode('catalog')}>사진 업로드 · 직접 선택</button>
        <button type="button" aria-pressed={activeMode==='recommendation'} disabled={task.busy||!hair} onClick={()=>changeMode('recommendation')}>헤어 추천에서 가져오기</button>
      </div>
      {!hair&&<p className="input-note">헤어 추천 결과도 사용할 수 있어요. <a href="#/hair">얼굴형 · 헤어 추천 받기</a></p>}
    </section>
    {activeMode==='catalog'?<section className="form-card">
      <div className="card-heading"><span className="step-number">01</span><div><h3>합성할 사진</h3><p>정면 얼굴 사진 1장 · 최대 10MB</p></div></div>
      <PhotoUpload files={photos} onChange={selectPhotos} disabled={task.busy}/>
      {photoError&&<p role="alert" className="error-box">{photoError}</p>}
    </section>:<section className="form-card">
      <div className="card-heading"><span className="step-number">01</span><div><h3>헤어 추천 사진과 스타일</h3><p>얼굴형 분석 #{hair!.analysis.id} · {hair!.analysis.face_shape} 추천 결과</p></div></div>
      <p className="input-note">추천에 사용한 정면 사진: {hair!.photo.name}</p>
    </section>}
    <section className="form-card">
      <div className="card-heading"><span className="step-number">02</span><div><h3>{activeMode==='catalog'?'카탈로그에서 스타일 선택':'추천 스타일 선택'}</h3><p>입어 보고 싶은 스타일을 골라 주세요.</p></div></div>
      {activeMode==='catalog'&&<>
        <fieldset className="studio-catalog-filters" disabled={task.busy||loading}><legend className="sr-only">카탈로그 필터</legend>
          <label className="field">스타일 구분<select value={sex} onChange={e=>changeFilter(setSex,e.target.value)}><option value="">전체</option>{['female','male','unisex'].map(value=><option key={value} value={value}>{labels[value]}</option>)}</select></label>
          <label className="field">길이<select value={length} onChange={e=>changeFilter(setLength,e.target.value)}><option value="">전체</option>{[...new Set(styles.map(item=>item.length))].map(value=><option key={value} value={value}>{labels[value]??value}</option>)}</select></label>
          <label className="field">질감<select value={texture} onChange={e=>changeFilter(setTexture,e.target.value)}><option value="">전체</option>{[...new Set(styles.map(item=>item.texture))].map(value=><option key={value} value={value}>{labels[value]??value}</option>)}</select></label>
        </fieldset>
        {loading&&<p role="status">스타일 카탈로그를 불러오는 중…</p>}
        {catalogError&&<p role="alert" className="error-box">카탈로그 조회 실패: {catalogError} <button type="button" onClick={()=>setRevision(value=>value+1)}>다시 조회</button></p>}
        {!loading&&!catalogError&&!visible.length&&<p className="empty-box">{styles.length?'선택한 조건에 맞는 스타일이 없습니다. 필터를 바꿔 주세요.':'등록된 헤어스타일이 없습니다.'}</p>}
      </>}
      <fieldset className="studio-styles" disabled={task.busy||(activeMode==='catalog'&&(loading||!!catalogError))}><legend className="sr-only">합성할 헤어스타일</legend>
        {(activeMode==='recommendation'?recs:visible).map(item=><label key={item.style_id} className={`studio-style${item.style_id===selected?.style_id?' selected':''}`}>
          <input type="radio" name="studio-style" value={item.style_id} checked={item.style_id===selected?.style_id} onChange={()=>{clearResult();if(activeMode==='recommendation')setRecommendedId(item.style_id);else setCatalogId(item.style_id)}}/>
          {item.image?<img src={item.image} alt="" loading="lazy"/>:<span className="image-placeholder"/>}
          <span><small>{'rank' in item?`추천 ${item.rank}`:`${labels[item.sex]??item.sex} · ${labels[item.length]??item.length}`}</small>{item.name}</span>
        </label>)}
      </fieldset>
      {activeMode==='recommendation'&&!recs.length&&<p className="empty-box">추천 스타일이 없습니다. 직접 선택을 이용해 주세요.</p>}
      <button className="recommend-button" type="button" disabled={!ready} onClick={start}>{task.busy?'합성하고 있어요…':'AI로 헤어 합성하기'}<Icon name="arrow" size={18}/></button>
      <p className="input-note">사진은 합성을 위해 Google AI로 전송됩니다. 비회원은 하루 이용 횟수가 정해져 있어요.</p>
    </section>
    {task.busy&&<div className="request-progress" role="status"><span className="spinner"/><div><strong>{selected?.name} 합성 중…</strong><p>잠시만 기다려 주세요.</p></div></div>}
    <TaskStatus busy={false} error={task.error}/>
    {render&&<section className="form-card"><div className="card-heading"><span className="step-number">03</span><div><h3>머리색 바꿔보기</h3><p>{render.styleName} · 색을 누르면 바로 바뀌어요.</p></div></div><HairColorStudio render={render.value} styleName={render.styleName}/></section>}
  </section>
}
