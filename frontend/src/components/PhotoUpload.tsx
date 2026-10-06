import { useId, useRef, useState } from 'react'
import PhotoPreview from './PhotoPreview'
import Icon from './Icon'

export default function PhotoUpload({ files, onChange, multiple = false, disabled = false }: { files: File[]; onChange: (files: File[]) => void; multiple?: boolean; disabled?: boolean }) {
  const input = useRef<HTMLInputElement>(null)
  const id = useId()
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  function select(next: File[]) {
    if (disabled) return
    setError('')
    if (next.some(file => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type))) { setError('JPG, PNG, WEBP 사진을 선택해 주세요.'); return }
    if (next.length > (multiple ? 3 : 1)) { setError(multiple ? '사진은 최대 3장까지 선택할 수 있습니다.' : '정면 사진 1장을 선택해 주세요.'); return }
    onChange(next)
  }
  return <div className="upload-control">
    <div className={`upload-zone${dragging ? ' dragging' : ''}${disabled ? ' disabled' : ''}`}
      onDragOver={event => { event.preventDefault(); if (!disabled) setDragging(true) }}
      onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); if (disabled) return; const next = Array.from(event.dataTransfer.files); if (next.length) select(next); else setError('사진 파일을 끌어 놓아 주세요.') }}>
      <span className="upload-icon"><Icon name="upload" size={27} /></span>
      <strong>{multiple ? '얼굴 사진을 선택해 주세요' : '정면 얼굴 사진을 올려 주세요'}</strong>
      <p>{multiple ? '정면 1장 또는 정면·좌·우 3장' : '얼굴이 잘 보이는 사진 1장'}<br />사진을 끌어 놓거나 아래 버튼을 눌러 주세요.</p>
      <label className="button upload-button" htmlFor={id}>{files.length ? '사진 다시 선택' : '사진 선택'}<input ref={input} id={id} className="file-picker" type="file" accept="image/jpeg,image/png,image/webp" multiple={multiple} disabled={disabled}
        aria-label={multiple ? '얼굴 사진 · 1장 또는 3장' : '정면 얼굴 사진'}
        onChange={event => { const next = Array.from(event.target.files ?? []); if (next.length) select(next); event.target.value = '' }} /></label>
      <small>JPG · PNG · WEBP</small>
    </div>
    {error && <p role="alert" className="error-box">{error}</p>}
    {multiple && files.length === 2 && <p role="status" className="photo-count-note">현재 2장입니다. 분석하려면 정면 1장만 남기거나, ‘사진 다시 선택’에서 정면·좌·우 3장을 함께 선택해 주세요.</p>}
    {files.length > 0 && <div className="selected-photos"><div className="selected-heading"><span>{files.length}장 선택됨</span><button type="button" className="text-button" disabled={disabled} onClick={() => { select([]); if (input.current) input.current.value = '' }}>전체 지우기</button></div>
      <div className="photo-strip">{files.map((file, index) => <div className="photo-item" key={`${file.name}:${file.lastModified}:${index}`}><PhotoPreview file={file} /><button type="button" className="remove-photo" aria-label={`${index + 1}번째 사진 삭제`} disabled={disabled} onClick={() => select(files.filter((_, i) => i !== index))}><Icon name="close" size={14} /></button></div>)}</div>
    </div>}
    <p className="photo-tip"><Icon name="info" size={16} />밝은 곳에서 얼굴을 가리지 않고 촬영하면 분석에 도움이 됩니다.</p>
  </div>
}
