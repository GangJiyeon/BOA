import { useEffect, useState } from 'react'
import { changeConsent, deleteMember, getConsents, termNames, type ConsentStatus } from '../api/account'
import type { useTask } from '../hooks/useTask'

type Props = {
  task: ReturnType<typeof useTask>
  onMessage: (message: string) => void
  onDeleted: () => Promise<void>
}

export default function AccountPreferences({ task, onMessage, onDeleted }: Props) {
  const [consents, setConsents] = useState<ConsentStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [revision, setRevision] = useState(0)
  const [confirming, setConfirming] = useState(false)
  const [confirmed, setConfirmed] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setLoadError(''); setConsents([])
    getConsents(controller.signal).then(value => {
      if (!controller.signal.aborted) setConsents(value)
    }).catch((err: unknown) => {
      if (!controller.signal.aborted) setLoadError(err instanceof Error ? err.message : '동의 정보를 불러오지 못했습니다.')
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [revision])

  function toggle(consent: ConsentStatus) {
    onMessage('')
    void task.run(async signal => {
      // 성공 응답을 받은 뒤에만 체크 상태를 바꾼다. 실패하면 기존 상태를 유지한다.
      const value = await changeConsent(consent.type, consent.agreed ? 'WITHDRAW' : 'AGREE', signal)
      if (signal.aborted) return
      setConsents(current => current.map(item => item.type === value.type ? value : item))
      onMessage(`${termNames[value.type] ?? value.type} ${value.agreed ? '동의를 저장했습니다.' : '동의를 철회했습니다.'}`)
    })
  }

  function withdraw() {
    if (!confirmed || task.busy) return
    onMessage('')
    void task.run(async signal => {
      await deleteMember(signal)
      if (!signal.aborted) await onDeleted()
    })
  }

  return <>
    <section className="account-preferences" aria-labelledby="account-consents-title">
      <h4 id="account-consents-title">약관 동의 관리</h4>
      <p className="input-note">선택 항목은 언제든 변경할 수 있습니다. 필수 약관에 더 이상 동의하지 않으면 회원 탈퇴를 이용해 주세요.</p>
      {loading && <p role="status">동의 정보를 불러오는 중입니다.</p>}
      {loadError && <p role="alert" className="error-box">{loadError} <button type="button" disabled={task.busy} onClick={() => setRevision(value => value + 1)}>동의 정보 다시 조회</button></p>}
      {!loading && !loadError && (consents.length ? <>
        <div className="account-optional-consents">{consents.filter(consent => !consent.required).map(consent => <label className="check-row account-consent-row" key={consent.type}>
          <span>{termNames[consent.type] ?? consent.type}<small>{consent.agreed ? '동의 중' : '동의하지 않음'}</small></span>
          <input type="checkbox" checked={consent.agreed} disabled={task.busy || confirming} onChange={() => toggle(consent)} />
        </label>)}</div>
        {consents.some(consent => consent.required) && <details className="account-required-consents"><summary>필수 약관 동의 내역</summary>
          {consents.filter(consent => consent.required).map(consent => <label className="check-row" key={consent.type}>
            <input type="checkbox" checked={consent.agreed} disabled />{termNames[consent.type] ?? consent.type}{consent.version ? ` · ${consent.version}` : ''}
          </label>)}
        </details>}
      </> : <p>현재 등록된 약관이 없습니다.</p>)}
    </section>
    <section className="account-withdraw" aria-labelledby="account-withdraw-title">
      <h4 id="account-withdraw-title">회원 탈퇴</h4>
      {!confirming ? <button type="button" className="secondary" disabled={task.busy} onClick={() => { task.reset(); onMessage(''); setConfirmed(false); setConfirming(true) }}>회원 탈퇴</button> : <>
        <p>탈퇴하면 회원 정보와 계정에 연결된 분석 기록이 삭제되며 복구할 수 없습니다.</p>
        <label className="check-row"><input type="checkbox" checked={confirmed} disabled={task.busy} onChange={event => setConfirmed(event.target.checked)} />삭제 내용을 확인했으며 탈퇴에 동의합니다.</label>
        <div className="actions">
          <button type="button" className="secondary" disabled={task.busy} onClick={() => { task.reset(); setConfirmed(false); setConfirming(false) }}>탈퇴 취소</button>
          <button type="button" className="account-delete-button" disabled={task.busy || !confirmed} onClick={withdraw}>확인하고 탈퇴하기</button>
        </div>
      </>}
    </section>
  </>
}
