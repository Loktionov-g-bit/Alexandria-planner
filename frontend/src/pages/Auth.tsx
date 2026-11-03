import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { QRCodeSVG } from 'qrcode.react'
import { api, ApiError, type Me } from '../api'
import { errorText, useSetMe } from '../session'
import { AuthorLinks } from '../Shell'
import { baseLogin } from '../names'

const DECO = [
  { q: 'plan', cls: 'd1', mount: 'tape' },
  { q: 'delegate', cls: 'd2', mount: 'pin pin-blue' },
  { q: 'do', cls: 'd3', mount: 'magnet pin-green' },
  { q: 'drop', cls: 'd4', mount: 'tape washi-blue' },
  { q: 'inbox', cls: 'd5', mount: 'pin pin-violet' },
] as const
const TONES = { do: 'tone-q1', plan: 'tone-q2', delegate: 'tone-q3', drop: 'tone-q4', inbox: 'tone-inbox' }

/** Login, setup and 2FA screens: the form is a sheet of paper taped to the desk. */
function AuthCard({ title, lead, children }: { title: string; lead?: string; children: ReactNode }) {
  const { t } = useTranslation()
  const deco = t('authDesk.deco', { returnObjects: true }) as string[]
  const kinds = t('authDesk.kinds', { returnObjects: true }) as string[]
  return (
    <div className="desk">
      {DECO.map((d, i) => (
        <div key={d.cls} className={`deco ${d.cls} ${TONES[d.q]}`} aria-hidden>
          <span className={`att ${d.mount}`} />
          <small>{kinds[i]}</small>{deco[i]}
        </div>
      ))}
      <div className="sheet-paper">
        <span className="att tape wide" aria-hidden />
        <div className="logo">
          <img src="alexandria-planner-logo.svg" alt="" />
          <div><b>{t('app.brand')}</b><span>{t('app.name')}</span></div>
        </div>
        {title && <h1>{title}</h1>}
        {lead && <p className="lead">{lead}</p>}
        {children}
      </div>
      <AuthorLinks className="desk-foot" />
    </div>
  )
}

function useSubmit<T>(fn: () => Promise<T>, done: (r: T) => void) {
  const { t } = useTranslation()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      done(await fn())
    } catch (err) {
      setError(errorText(t, err))
    } finally {
      setBusy(false)
    }
  }
  return { submit, error, busy }
}

export function SetupPage() {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const setMe = useSetMe()
  const [mode, setMode] = useState<'team' | 'solo' | null>(null)
  const [f, setF] = useState({ department: '', login: '', first_name: '', last_name: '', password: '', password2: '', is_manager: true })
  const [loginTouched, setLoginTouched] = useState(false)
  const login = loginTouched ? f.login : baseLogin(f.first_name, f.last_name)
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const { submit, error, busy } = useSubmit(
    () => {
      if (f.password !== f.password2) return Promise.reject(new ApiError(0, 'error.mismatch'))
      const { password2, ...body } = f
      void password2
      return api<Me>('setup', {
        body: { ...body, mode, login, locale: i18n.language, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone },
      })
    },
    (me) => {
      setMe(me)
      qc.setQueryData(['setup'], { needed: false })
    },
  )

  return (
    <AuthCard title={t('setup.title')} lead={mode ? t('setup.lead') : t('setup.modeLead')}>
      {!mode ? (
        <div className="modes" role="radiogroup" aria-label={t('setup.modeLead')}>
          {(['team', 'solo'] as const).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={false} className={`modecard m-${m}`} onClick={() => setMode(m)}>
              <span className="mi" aria-hidden>
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  {m === 'team'
                    ? <><circle cx="9" cy="8" r="3.2" /><path d="M3 19c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5" /><circle cx="17" cy="9" r="2.6" /><path d="M16 13.6c2.9.1 5 2 5 4.9" /></>
                    : <><path d="M6 3.5h11a1.5 1.5 0 0 1 1.5 1.5v14.5a1 1 0 0 1-1 1H6.5A2 2 0 0 1 4.5 18.5V5A1.5 1.5 0 0 1 6 3.5z" /><path d="M8 3.5v17M11 8h4.5M11 11.5h3" /></>}
                </svg>
              </span>
              <b>{t(`setup.mode.${m}`)}</b>
              <small>{t(`setup.mode.${m}Hint`)}</small>
            </button>
          ))}
          <p className="small muted">{t('setup.modeLater')}</p>
        </div>
      ) : (
      <form className="stack" onSubmit={submit}>
        <button type="button" className="linkish" onClick={() => setMode(null)}>← {t(`setup.mode.${mode}`)} · {t('setup.modeChange')}</button>
        {mode === 'team' && <label className="field">{t('setup.department')}<input required value={f.department} onChange={set('department')} /></label>}
        <div className="grid2">
          <label className="field">{t('admin.firstName')}<input required value={f.first_name} onChange={set('first_name')} /></label>
          <label className="field">{t('admin.lastName')}<input required value={f.last_name} onChange={set('last_name')} /></label>
        </div>
        <label className="field">{t('setup.login')}
          <input required autoComplete="username" pattern="[A-Za-z0-9._\-]+" value={login}
            onChange={(e) => { setLoginTouched(true); setF({ ...f, login: e.target.value }) }} />
          <span className="small muted">{t('admin.loginHint')}</span>
        </label>
        <label className="field">{t('setup.password')}<input required type="password" autoComplete="new-password" value={f.password} onChange={set('password')} /></label>
        <label className="field">{t('setup.password2')}<input required type="password" autoComplete="new-password" value={f.password2} onChange={set('password2')} /></label>
        <span className="muted small">{t('password.hint')}</span>
        {mode === 'team' && <label className="check"><input type="checkbox" checked={f.is_manager} onChange={set('is_manager')} />{t('setup.isManager')}</label>}
        {error && <div className="error">{error}</div>}
        <button className="primary big" disabled={busy}>{t('setup.submit')}</button>
      </form>
      )}
    </AuthCard>
  )
}

export function LoginPage() {
  const { t } = useTranslation()
  const setMe = useSetMe()
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const { submit, error, busy } = useSubmit(() => api<Me>('auth/login', { body: { login, password } }), setMe)
  return (
    <AuthCard title="">
      <form className="stack" onSubmit={submit} aria-label={t('login.title')}>
        <label className="field">{t('login.login')}<input required autoFocus autoComplete="username" value={login} onChange={(e) => setLogin(e.target.value)} /></label>
        <label className="field">{t('login.password')}<input required type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {error && <div className="error">{error}</div>}
        <button className="primary big" disabled={busy}>{t('login.submit')}</button>
        <p className="help">{t('login.forgot')}</p>
      </form>
    </AuthCard>
  )
}

export function TotpPage({ me }: { me: Me }) {
  const { t } = useTranslation()
  const setMe = useSetMe()
  const enroll = me.pending === 'totp_setup'
  const [code, setCode] = useState('')
  const [setup, setSetup] = useState<{ secret: string; uri: string } | null>(null)
  useEffect(() => {
    if (enroll) api<{ secret: string; uri: string }>('auth/totp/setup', { method: 'POST' }).then(setSetup)
  }, [enroll])
  const { submit, error, busy } = useSubmit(
    () => api<Me>(enroll ? 'auth/totp/enable' : 'auth/totp', { body: { code } }),
    setMe,
  )
  const logout = async () => {
    await api('auth/logout', { method: 'POST' })
    setMe(null)
  }
  return (
    <AuthCard title={enroll ? t('totp.setupTitle') : t('totp.title')} lead={enroll ? t('totp.setupLead') : t('totp.lead')}>
      <form className="stack" onSubmit={submit}>
        {enroll && setup && (
          <>
            <div className="qr"><QRCodeSVG value={setup.uri} size={176} /></div>
            <details>
              <summary className="muted small">{t('totp.manual')}</summary>
              <p className="secret">{setup.secret}</p>
            </details>
          </>
        )}
        <label className="field">{t('totp.code')}
          <input required autoFocus inputMode="numeric" autoComplete="one-time-code" maxLength={8} value={code} onChange={(e) => setCode(e.target.value)} />
        </label>
        {error && <div className="error">{error}</div>}
        <div className="row">
          <button type="button" className="ghost" onClick={logout}>{t('totp.cancel')}</button>
          <span className="spacer" />
          <button className="primary" disabled={busy}>{enroll ? t('totp.enable') : t('totp.submit')}</button>
        </div>
      </form>
    </AuthCard>
  )
}
