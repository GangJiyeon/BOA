import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import Icon from './Icon'

function cameraError(error: unknown) {
  const name = error instanceof Error ? error.name : ''
  if (name === 'NotAllowedError') return '카메라 권한을 허용해 주세요. 주소창의 카메라 권한을 확인하거나 사진 선택을 이용할 수 있습니다.'
  if (name === 'NotFoundError') return '연결된 카메라가 없습니다. 사진 선택으로 이미지를 올려 주세요.'
  if (name === 'NotReadableError') return '카메라를 사용할 수 없습니다. 다른 앱에서 사용 중인지 확인해 주세요.'
  return '카메라를 시작하지 못했습니다. 다시 시도하거나 사진 선택을 이용해 주세요.'
}

export default function CameraCapture({ onCapture, onClose }: { onCapture: (file: File) => void; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const video = useRef<HTMLVideoElement>(null)
  const activeSession = useRef({ cancelled: true })
  const [facing, setFacing] = useState<'user' | 'environment'>('user')
  const [attempt, setAttempt] = useState(0)
  const [ready, setReady] = useState(false)
  const [taking, setTaking] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const modal = dialog.current
    modal?.showModal()
    return () => modal?.close()
  }, [])
  useEffect(() => {
    const hide = () => { if (document.hidden) onClose() }
    window.addEventListener('hashchange', onClose)
    document.addEventListener('visibilitychange', hide)
    return () => { window.removeEventListener('hashchange', onClose); document.removeEventListener('visibilitychange', hide) }
  }, [onClose])
  useEffect(() => {
    const session = { cancelled: false }
    activeSession.current = session
    let acquiredStream: MediaStream | null = null
    async function start() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError('이 주소에서는 카메라를 사용할 수 없습니다. localhost 또는 HTTPS로 접속하거나 사진 선택을 이용해 주세요.')
        return
      }
      try {
        const acquired = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: facing }, width: { ideal: 1280 }, height: { ideal: 960 } } })
        if (session.cancelled) { acquired.getTracks().forEach(track => track.stop()); return }
        acquiredStream = acquired
        if (video.current) { video.current.srcObject = acquired; await video.current.play() }
      } catch (err) {
        if (!session.cancelled) { acquiredStream?.getTracks().forEach(track => track.stop()); acquiredStream = null; setReady(false); setError(cameraError(err)) }
      }
    }
    void start()
    return () => { session.cancelled = true; acquiredStream?.getTracks().forEach(track => track.stop()) }
  }, [facing, attempt])

  function capture() {
    if (!ready || taking || !video.current?.videoWidth) return
    const session = activeSession.current
    const canvas = document.createElement('canvas')
    canvas.width = video.current.videoWidth; canvas.height = video.current.videoHeight
    const context = canvas.getContext('2d')
    if (!context) { setError('사진을 만들 수 없습니다. 사진 선택을 이용해 주세요.'); return }
    setTaking(true)
    // 사용자가 본 셀프 카메라 화면과 저장 사진의 좌우 방향을 맞춘다.
    if (facing === 'user') { context.translate(canvas.width, 0); context.scale(-1, 1) }
    context.drawImage(video.current, 0, 0)
    canvas.toBlob(blob => {
      if (session.cancelled) return
      setTaking(false)
      if (!blob) { setError('촬영한 사진을 저장하지 못했습니다. 다시 촬영해 주세요.'); return }
      onCapture(new File([blob], `boa-photo-${Date.now()}.jpg`, { type: 'image/jpeg' }))
      onClose()
    }, 'image/jpeg', 0.92)
  }

  return createPortal(<dialog ref={dialog} className="camera-dialog" aria-labelledby="camera-title" onCancel={event => { event.preventDefault(); onClose() }}>
    <div className="camera-heading"><div><h2 id="camera-title">사진 찍기</h2><p>얼굴 전체가 보이도록 정면을 바라봐 주세요.</p></div><button type="button" className="secondary" aria-label="카메라 닫기" onClick={onClose}><Icon name="close" /></button></div>
    <div className="camera-view"><video ref={video} autoPlay playsInline muted className={facing === 'user' ? 'mirrored' : ''} onLoadedData={() => setReady(true)} /><div className="camera-guide" aria-hidden="true" /></div>
    {error ? <div className="error-box" role="alert">{error}<button type="button" className="secondary" onClick={() => { setError(''); setReady(false); setAttempt(n => n + 1) }}>다시 시도</button></div>
      : !ready && <p role="status">카메라를 준비하고 있어요. 권한 요청이 뜨면 허용해 주세요.</p>}
    <div className="camera-actions"><button type="button" className="secondary" disabled={taking} onClick={() => { setReady(false); setError(''); setFacing(value => value === 'user' ? 'environment' : 'user') }}>카메라 전환</button><button type="button" disabled={!ready || taking || !!error} onClick={capture}>{taking ? '사진 처리 중…' : '촬영하기'}</button><button type="button" className="text-button" onClick={onClose}>취소</button></div>
    <p className="input-note">촬영하면 미리보기에서 확인할 수 있습니다. 분석 시작 전에는 서버로 전송하지 않습니다.</p>
  </dialog>, document.body)
}
