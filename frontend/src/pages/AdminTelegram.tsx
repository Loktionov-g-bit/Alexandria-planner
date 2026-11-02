import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError } from '../api'
import { errorText } from '../session'

interface TgStatus { configured: boolean; username: string | null; token: string | null }

/** Admin: connect the company's own bot. The token stays on the server; only a mask comes back. */
export default function AdminTelegram() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const st = useQuery({ queryKey: ['admin', 'telegram'], queryFn: () => api<TgStatus>('admin/telegram') })
  const [token, setToken] = useState('')
  const [replace, setReplace] = useState(false)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const run = async (fn: () => Promise<unknown>, okText: string) => {
    setBusy(true)
    setMsg(null)
    try {
      await fn()
      setMsg({ ok: true, text: okText })
      qc.invalidateQueries({ queryKey: ['admin', 'telegram'] })
    } catch (e) {
      // a token that does not even look like one fails validation: say so plainly
      const bad = e instanceof ApiError && e.status === 422 && e.keys.includes('error.validation')
      setMsg({ ok: false, text: bad ? t('telegram.bad_token') : errorText(t, e) })
    } finally {
      setBusy(false)
    }
  }
  const save = (e: FormEvent) => {
    e.preventDefault()
    run(async () => { await api('admin/telegram', { method: 'PUT', body: { token: token.trim() } }); setToken(''); setReplace(false) }, t('tg.saved'))
  }
  if (!st.data) return null
  const d = st.data
  return (
    <div className="tgadmin stack">
      {d.configured && !replace ? (
        <div className="card stack">
          <div className="pline">
            <div className="w"><b>{t('tg.connected', { name: d.username })}</b><small>{t('tg.tokenMasked', { token: d.token })}</small></div>
            <span className="state"><span className="dot ok" aria-hidden />{t('tg.on')}</span>
          </div>
          <div className="actions">
            <button className="btn" type="button" disabled={busy} onClick={() => run(() => api('admin/telegram/check', { method: 'POST' }), t('tg.checkOk'))}>{t('tg.check')}</button>
            <button className="btn" type="button" onClick={() => setReplace(true)}>{t('tg.replace')}</button>
            <button className="btn danger" type="button" disabled={busy} onClick={() => run(() => api('admin/telegram', { method: 'DELETE' }), t('tg.removed'))}>{t('tg.remove')}</button>
          </div>
          <p className="hint">{t('tg.groupHint', { name: d.username })}</p>
          {msg && <p className={msg.ok ? 'notice' : 'error'}>{msg.text}</p>}
        </div>
      ) : (
        <div className="card stack">
          <h2>{t('tg.howTitle')}</h2>
          <ol className="steps-list">
            <li>{t('tg.step1')} <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">@BotFather</a>.</li>
            <li>{t('tg.step2')}</li>
            <li>{t('tg.step3')}</li>
            <li>{t('tg.step4')}</li>
          </ol>
          <form className="actions" onSubmit={save}>
            <label htmlFor="tg-token" className="sr">{t('tg.token')}</label>
            <input id="tg-token" className="token" required autoComplete="off" spellCheck={false} placeholder="123456789:AAH…" value={token} onChange={(e) => setToken(e.target.value)} />
            <button className="btn primary" disabled={busy || !token.trim()}>{t('tg.connect')}</button>
            {replace && <button type="button" className="btn" onClick={() => setReplace(false)}>{t('common.cancel')}</button>}
          </form>
          <p className="hint">{t('tg.privacy')}</p>
          {msg && <p className={msg.ok ? 'notice' : 'error'}>{msg.text}</p>}
        </div>
      )}
      <TunnelCard />
    </div>
  )
}

interface TunnelStatus {
  configured: boolean
  mode: 'auto' | 'always' | 'off'
  endpoint?: string
  address?: string
  name?: string
  running: boolean
  route: 'direct' | 'tunnel'
  last_ok: number | null
  last_error: string | null
  binary: boolean
}
interface Probe { ok: boolean; status?: number; error?: string }

async function uploadTunnel(file: File): Promise<TunnelStatus> {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch('api/admin/telegram/tunnel', { method: 'PUT', body: fd, credentials: 'same-origin' })
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? null)
  return data as TunnelStatus
}

/** Backup route: a WireGuard config used only for talking to Telegram, when the direct route is blocked. */
function TunnelCard() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const st = useQuery({ queryKey: ['admin', 'tunnel'], queryFn: () => api<TunnelStatus>('admin/telegram/tunnel'), refetchInterval: 30_000 })
  const fileRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const run = async (fn: () => Promise<string>) => {
    setBusy(true)
    setMsg(null)
    try {
      setMsg({ ok: true, text: await fn() })
    } catch (e) {
      setMsg({ ok: false, text: errorText(t, e) })
    } finally {
      setBusy(false)
      qc.invalidateQueries({ queryKey: ['admin', 'tunnel'] })
    }
  }
  const pick = (f: File | undefined) => {
    if (fileRef.current) fileRef.current.value = ''
    if (f) run(async () => { await uploadTunnel(f); return t('tunnel.saved') })
  }
  const check = () => run(async () => {
    const r = await api<{ direct: Probe; tunnel: Probe }>('admin/telegram/tunnel/check', { method: 'POST' })
    const yn = (p: Probe) => (p.ok ? t('tunnel.yes') : t('tunnel.no'))
    return t('tunnel.checkResult', { direct: yn(r.direct), tunnel: d.configured ? yn(r.tunnel) : t('tunnel.notSet') })
  })
  if (!st.data) return null
  const d = st.data
  const routeKey = !d.configured || d.mode === 'off' ? null : d.route === 'tunnel' ? 'tunnel' : 'direct'
  return (
    <div className="card stack">
      <h2>{t('tunnel.title')}</h2>
      <p className="hint">{t('tunnel.lead')}</p>
      <input ref={fileRef} type="file" accept=".conf,.zip" className="sr" aria-label={t('tunnel.upload')} onChange={(e) => pick(e.target.files?.[0])} />
      {d.configured ? (
        <>
          <div className="pline">
            <div className="w"><b>{t('tunnel.file', { name: d.name })}</b><small>{t('tunnel.details', { endpoint: d.endpoint, address: d.address })}</small></div>
            {routeKey && <span className="state"><span className={`dot ${d.running || routeKey === 'direct' ? 'ok' : ''}`} aria-hidden />{t(`tunnel.route.${routeKey}`)}</span>}
          </div>
          <div className="seg" role="radiogroup" aria-label={t('tunnel.modeLabel')}>
            {(['auto', 'always', 'off'] as const).map((m) => (
              <button key={m} type="button" role="radio" aria-checked={d.mode === m} className={d.mode === m ? 'on' : ''} disabled={busy}
                onClick={() => run(async () => { await api('admin/telegram/tunnel', { method: 'PATCH', body: { mode: m } }); return t(`tunnel.modeHint.${m}`) })}>
                {t(`tunnel.mode.${m}`)}
              </button>
            ))}
          </div>
          <p className="hint">{t(`tunnel.modeHint.${d.mode}`)}</p>
          {!d.binary && <p className="error">{t('tunnel.noBinary')}</p>}
          {d.last_error && d.mode !== 'off' && <p className="hint">{t('tunnel.lastError', { error: d.last_error })}</p>}
          <div className="actions">
            <button className="btn" type="button" disabled={busy} onClick={check}>{t('tunnel.check')}</button>
            <button className="btn" type="button" disabled={busy} onClick={() => fileRef.current?.click()}>{t('tunnel.replace')}</button>
            <button className="btn danger" type="button" disabled={busy} onClick={() => run(async () => { await api('admin/telegram/tunnel', { method: 'DELETE' }); return t('tunnel.removed') })}>{t('tunnel.remove')}</button>
          </div>
        </>
      ) : (
        <div className="actions">
          <button className="btn primary" type="button" disabled={busy} onClick={() => fileRef.current?.click()}>{t('tunnel.upload')}</button>
          <button className="btn" type="button" disabled={busy} onClick={check}>{t('tunnel.checkDirect')}</button>
        </div>
      )}
      <p className="hint">{t('tunnel.keysHint')}</p>
      {msg && <p className={msg.ok ? 'notice' : 'error'}>{msg.text}</p>}
    </div>
  )
}
