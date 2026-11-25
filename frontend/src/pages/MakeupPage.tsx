import { useEffect, useRef, useState, type FormEvent } from 'react'
import PageIntro, { ProgressSteps } from '../components/PageIntro'
import PhotoUpload from '../components/PhotoUpload'
import Icon from '../components/Icon'
import { SectionJump } from '../components/Shared'
import MakeupStudio from '../components/MakeupStudio'
import { analyzeSkinTone, type SkinTone } from '../api/makeup'
import { BRIGHTNESS, FACE_SHAPES, MAKEUP_SEXES, TONES, brightnessFromAnalysis, cushionFromAnalysis, faceShapeFromAnalysis, type Brightness, type FaceShape, type MakeupSex, type Undertone } from '../studio/makeup-looks'
import type { HairSessionResult, StudioMakeupResult } from '../types/sessionResults'
import type { SessionPhotoProps } from '../hooks/useSessionPhoto'
import './MakeupPage.css'


// 얼굴형·헤어 추천 페이지와 같은 흐름: 01 사진 · 02 추천 기준 → 추천받기 → 03 결과
// 사진을 올리면 바로 피부톤 분석(/skin/tone)으로 톤·밝기·쿠션을 채움, 직접 고른 값이 있으면 덮어쓰지 않음, 실패하면 직접 고른 값으로 진행
export default function MakeupPage({hair,studioResult,onDiscardStudioResult,sessionPhoto,onPhoto}:SessionPhotoProps&{hair:HairSessionResult|null;studioResult:StudioMakeupResult|null;onDiscardStudioResult:()=>void}) {
  // 시작 사진: AI Studio 합성 사진 > 세션 사진(가장 최근에 올린 정면 사진) > 헤어 분석 사진
  const initialPhoto=studioResult?.photo??sessionPhoto??hair?.photo
  const [photos,setPhotos]=useState<File[]>(initialPhoto?[initialPhoto]:[])
  // 추천받기를 누른 사진 (사진을 바꾸면 다시 눌러야 결과가 바뀜, 톤·밝기·얼굴형은 결과를 보면서 바로 반영)
  const [submitted,setSubmitted]=useState<File|null>(null)
  // 헤어 분석에서 남성 스타일을 골랐으면 남성으로 시작
  const [sex,setSex]=useState<MakeupSex>(hair?.analysis.sex==='male'&&(!studioResult||hair.photo===studioResult.sourcePhoto)?'male':'female')
  const [tone,setTone]=useState<Undertone>('neutral'),[brightness,setBrightness]=useState<Brightness>('medium')
  // 피부톤 분석 결과 (분석한 사진과 함께), 톤·밝기를 직접 바꾸면 manual
  const [toneResult,setToneResult]=useState<{file:File;tone:SkinTone}|null>(null)
  const [toneFailure,setToneFailure]=useState<{file:File;message:string}|null>(null),[manual,setManual]=useState(false)
  // 분석 응답 시점의 직접 선택 여부 (effect 밖 최신값)
  const manualRef=useRef(false)
  useEffect(()=>{manualRef.current=manual},[manual])
  // 기본은 자동: 메이크업 사진의 얼굴형·코·광대 분석으로 (헤어 분석 얼굴형은 버튼으로 가져옴)
  const [faceShape,setFaceShape]=useState<FaceShape|'auto'>('auto')
  const file=photos[0]??null
  const imported=studioResult?.photo===file?studioResult:null
  const tonePhoto=imported?.sourcePhoto??file
  const analysisShape=faceShapeFromAnalysis(hair?.analysis.face_shape)
  const usingAnalysis=Boolean(hair&&file===hair.photo&&analysisShape===faceShape)
  const done=Boolean(submitted&&submitted===file)
  const analyzed=toneResult&&toneResult.file===file?toneResult.tone:null
  // 분석 중 = 이 사진의 결과도 오류도 아직 없음
  const toneError=toneFailure&&toneFailure.file===file?toneFailure:null
  const toneBusy=Boolean(file&&!analyzed&&!toneError)
  // 쿠션: 베이스(황조·핑크조·뉴트럴)와 호수 모두 백엔드 피부톤 분석값 (추정 호수 ±2 범위의 가운데 = 화면 문구와 같은 호수)
  // 2026-11-18: 예전엔 호수를 메이크업 밝기(19·21·23호)로 덮어써 화면 문구와 실제 적용 호수가 달랐음
  // 톤·밝기를 직접 바꾸면 분석 쿠션은 안 씀
  const analyzedCushion=analyzed&&!manual?cushionFromAnalysis(analyzed.palette.cushion):undefined
  const cushion=analyzedCushion
  // 새 사진은 분석값을 다시 받음
  function resetManual(){setManual(false);manualRef.current=false}
  function changePhoto(files:File[]){
    if(imported&&files[0]!==imported.photo)onDiscardStudioResult()
    setPhotos(files);setSubmitted(null);resetManual()
    // 합성 사진은 세션 사진으로 안 씀
    if(files[0]!==studioResult?.photo)onPhoto?.(files[0]??null,file===studioResult?.photo?null:file)
  }
  function applyTone(result:SkinTone){setTone(result.undertone);setBrightness(brightnessFromAnalysis(result.brightness_level,result.raw?.ita_deg));setManual(false)}
  // 사진이 바뀌면 바로 분석 (이전 요청은 취소), 분석 중에 직접 고르면 그 값 유지
  useEffect(()=>{
    if(!file||!tonePhoto)return
    const controller=new AbortController()
    analyzeSkinTone(tonePhoto,controller.signal).then(result=>{
      if(controller.signal.aborted)return
      setToneResult({file,tone:result})
      if(!manualRef.current)applyTone(result)
    }).catch(err=>{if(!controller.signal.aborted)setToneFailure({file,message:err instanceof Error?err.message:'피부톤을 분석하지 못했어요.'})})
    return()=>controller.abort()
  },[file,tonePhoto])
  function submit(event:FormEvent){
    event.preventDefault()
    if(!file)return
    setSubmitted(file)
    requestAnimationFrame(()=>document.getElementById('makeup-result-title')?.scrollIntoView({behavior:'smooth',block:'start'}))
  }
  return <section className="makeup-page"><PageIntro eyebrow="MAKEUP" title="나에게 맞는 메이크업">피부 톤과 얼굴형에 맞는 메이크업을 입혀 보고, 부위별 강도를 조절해 보세요.</PageIntro>
    <ProgressSteps labels={['사진 입력','기준 선택','메이크업 추천']} current={done?3:file?1:0}/>
    <form onSubmit={submit}><fieldset className="analysis-fieldset"><legend className="sr-only">메이크업 추천 입력</legend><div className="analysis-layout">
      <section className="form-card input-panel"><div className="card-heading"><span className="step-number">01</span><div><h3>메이크업할 사진</h3><p>정면 얼굴 사진 1장 · 사진은 저장하지 않아요.</p></div></div>
        {imported&&<p className="input-note" role="status">AI Studio 합성 사진 · {imported.styleName}</p>}
        <PhotoUpload files={photos} onChange={changePhoto}/>
      </section>
      <section className="form-card options-panel makeup-setup"><div className="card-heading"><span className="step-number">02</span><div><h3>추천 기준</h3><p>사진으로 피부 톤·밝기를 분석하고, 얼굴형에 맞춰 메이크업을 골라 드려요.</p></div></div>
        <label className="field">스타일 구분<select value={sex} onChange={e=>setSex(e.target.value as MakeupSex)}>{MAKEUP_SEXES.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        <label className="field">피부 톤<select value={tone} onChange={e=>{setTone(e.target.value as Undertone);setManual(true)}}>{TONES.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        <label className="field">피부 밝기<select value={brightness} onChange={e=>{setBrightness(e.target.value as Brightness);setManual(true)}}>{BRIGHTNESS.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        <p className="input-note makeup-season-note">{TONES.find(item=>item.id===tone)!.description}</p>
        {analyzed&&<div className="makeup-tone-result" role="status">
          <p className="makeup-tone-name"><strong>{analyzed.palette.tone_name}</strong>{analyzed.confidence==='low'&&<span className="makeup-tone-low">정확도 낮음</span>}{manual&&<span className="makeup-tone-manual">직접 선택 중</span>}</p>
          <p>{analyzed.palette.point}</p>
          <dl><div><dt>립</dt><dd>{analyzed.palette.lip.join(' · ')}</dd></div><div><dt>블러셔</dt><dd>{analyzed.palette.blush.join(' · ')}</dd></div><div><dt>섀도</dt><dd>{analyzed.palette.eye.join(' · ')}</dd></div><div><dt>쿠션</dt><dd>{analyzed.palette.cushion}</dd></div></dl>
          {manual&&<button type="button" className="secondary" onClick={()=>applyTone(analyzed)}>분석값으로 되돌리기</button>}
          <ul className="makeup-tone-notices">{analyzed.notices.map(notice=><li key={notice}>{notice}</li>)}</ul>
        </div>}
        {toneBusy&&<p role="status" className="input-note">사진에서 피부 톤·밝기를 분석하고 있어요…</p>}
        {toneError&&<p role="alert" className="input-note makeup-tone-error">피부톤 분석 실패: {toneError.message} 직접 고른 톤·밝기로 보여 드려요.</p>}
        <label className="field">얼굴형<select value={faceShape} onChange={e=>setFaceShape(e.target.value as FaceShape|'auto')}><option value="auto">자동 (사진 분석)</option>{FACE_SHAPES.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        {hair&&<button type="button" className="secondary makeup-import" disabled={usingAnalysis} onClick={()=>{changePhoto([hair.photo]);if(analysisShape)setFaceShape(analysisShape)}}>{usingAnalysis?'이번 분석 사진·얼굴형 사용 중':imported?'원본 분석 사진과 얼굴형 가져오기':'이번 분석 사진과 얼굴형 가져오기'}</button>}
        <button className="recommend-button" type="submit" disabled={!file}>{done?'추천 메이크업을 보여 드리고 있어요':'얼굴 분석하고 메이크업 추천받기'}<Icon name="arrow" size={18}/></button>
        <p className="input-note">{hair?'톤·밝기·얼굴형은 결과를 보면서도 바꿀 수 있어요.':<>얼굴형 분석 결과도 사용할 수 있어요. <a href="#/hair">얼굴형 · 헤어 추천 받기</a></>}</p>
      </section>
    </div></fieldset></form>
    {done&&<div className="result-shortcut"><p role="status">메이크업 추천 완료 · {MAKEUP_SEXES.find(item=>item.id===sex)!.label} 메이크업</p><SectionJump targetId="makeup-result-title">결과로 이동</SectionJump></div>}
    {submitted&&<MakeupStudio file={submitted} profile={{tone,brightness,faceShape,sex,cushion}}/>}
  </section>
}
