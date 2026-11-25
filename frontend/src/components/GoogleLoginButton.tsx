import { GoogleOAuthProvider, useGoogleLogin } from '@react-oauth/google'

const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined

type Props = { disabled?: boolean; onCode: (code: string) => void; onError: (message: string) => void }

// 계정 화면에서만 GIS 스크립트 로드
export default function GoogleLoginButton(props: Props) {
  if (!clientId) return null
  return <GoogleOAuthProvider clientId={clientId}><CodeButton {...props} /></GoogleOAuthProvider>
}

function CodeButton({ disabled, onCode, onError }: Props) {
  // 백엔드 redirect_uri=postmessage 팝업 code flow
  const login = useGoogleLogin({
    flow: 'auth-code',
    onSuccess: ({ code }) => onCode(code),
    onError: () => onError('구글 로그인에 실패했습니다. 다시 시도해 주세요.'),
    onNonOAuthError: ({ type }) => { if (type !== 'popup_closed') onError('구글 로그인 창을 열지 못했습니다. 팝업 차단을 확인해 주세요.') },
  })
  return <button type="button" disabled={disabled} className="secondary" onClick={() => login()}>Google로 로그인</button>
}
