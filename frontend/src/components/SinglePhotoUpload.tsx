import { useCallback, useId, useState } from 'react'
import CameraCapture from './CameraCapture'
import PhotoFrame from './PhotoFrame'
import Icon from './Icon'

export default function SinglePhotoUpload({ file, onChange, disabled }: { file: File | null; onChange: (file: File | null) => void; disabled: boolean }) {
  const id = useId()
  const [camera, setCamera] = useState(false)
  const closeCamera = useCallback(() => setCamera(false), [])
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  function select(files: File[]) {
    if (disabled || !files.length) return
    if (files.length !== 1) { setError('정면 사진 1장을 선택해 주세요.'); return }
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(files[0].type)) { setError('JPG, PNG, WEBP 사진을 선택해 주세요.'); return }
    setError(''); setRevision(value => value + 1); onChange(files[0])
  }
  const actions = <div className="single-photo-actions">
    <button type="button" disabled={disabled} onClick={() => { setError(''); setCamera(true) }}><Icon name="camera" size={18} />{file ? '다시 찍기' : '사진 찍기'}</button>
    <label className="button secondary upload-button" htmlFor={id}><Icon name="upload" size={18} />{file ? '사진 변경' : '사진 선택'}<input id={id} type="file" className="file-picker" accept="image/jpeg,image/png,image/webp" disabled={disabled} aria-label="정면 얼굴 사진"
      onChange={event => { select(Array.from(event.target.files ?? [])); event.target.value = '' }} /></label>
    {file && <button type="button" className="text-button" disabled={disabled} onClick={() => { setError(''); onChange(null) }}>사진 삭제</button>}
  </div>
  return <div className={`single-photo-upload${dragging ? ' dragging' : ''}`}
    onDragOver={event => { event.preventDefault(); if (!disabled) setDragging(true) }} onDragLeave={() => setDragging(false)}
    onDrop={event => { event.preventDefault(); setDragging(false); const files = Array.from(event.dataTransfer.files); if (files.length) select(files); else if (!disabled) setError('사진 파일을 끌어 놓아 주세요.') }}>
    {file ? <><PhotoFrame key={revision} file={file} />{actions}</> : <div className="upload-zone single-upload-zone"><span className="upload-icon"><Icon name="camera" size={30} /></span><strong>얼굴 사진을 준비해 주세요</strong><p>카메라로 촬영하거나 사진을 선택하세요.<br />사진을 이곳에 끌어 놓아도 됩니다.</p>{actions}<small>JPG · PNG · WEBP</small></div>}
    {error && <p role="alert" className="error-box">{error}</p>}
    {camera && <CameraCapture onClose={closeCamera} onCapture={photo => select([photo])} />}
    <p className="photo-tip"><Icon name="info" size={16} />밝은 곳에서 얼굴을 가리지 않고 촬영해 주세요.</p>
  </div>
}
