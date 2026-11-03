import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { QRCodeSVG } from 'qrcode.react'
import { api, type Department, type Me, type User } from '../api'
import { errorText, useSetMe, useSolo } from '../session'
import { initials, isoDate, shortDate, useDirectory } from '../stickers'
import { LANGS, type Lang } from '../i18n'
import { intlLang, weekdays } from '../dates'
import { disablePush, enablePush, pushState, type PushState } from '../notifications'

const ZONES = (() => {
  try {
    return (Intl as unknown as { supportedValuesOf(k: string): string[] }).supportedValuesOf('timeZone')
  } catch {
    return ['Europe/Moscow', 'UTC']
  }
})()

function zoneLabel(z: string, lang: string) {
  let off = ''
  try {
    off = new Intl.DateTimeFormat(intlLang(lang), { timeZone: z, timeZoneName: 'shortOffset' }).formatToParts(new Date()).find((p) => p.type === 'timeZoneName')?.value ?? ''
  } catch { /* unknown zone */ }
  return `${z.split('/').pop()!.replace(/_/g, ' ')} (${off})`
}

/** PATCH /profile and update the session; returns a status line for the section. */
function useSaveProfile(me: Me) {
  const { t } = useTranslation()
  const setMe = useSetMe()
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null)
  const save = async (patch: Partial<User>): Promise<void> => {
    try {
      const user = await api<User>('profile', { method: 'PATCH', body: patch })
      setMe({ ...me, user })
      setStatus({ ok: true, text: t('profile.saved') })
    } catch (e) {
      setStatus({ ok: false, text: errorText(t, e) })
    }
  }
  useEffect(() => {
    if (!status?.ok) return
    const id = setTimeout(() => setStatus(null), 2000)
    return () => clearTimeout(id)
  }, [status])
  return { save, status }
}

const THEME_PREVIEW: Record<User['theme'], { bg: string; tones: string[] }> = {
  light: { bg: '#e9ecf0', tones: ['#f4b6a7', '#b7dcc2', '#f6d887', '#c5d1e3'] },
  dark: { bg: '#0f1114', tones: ['#5e3530', '#2b4a38', '#5a4a1e', '#2f3a4d'] },
  system: { bg: 'linear-gradient(135deg, #e9ecf0 50%, #0f1114 50%)', tones: ['#f4b6a7', '#b7dcc2', '#5a4a1e', '#2f3a4d'] },
}

function NameTag({ me }: { me: Me }) {
  const { t } = useTranslation()
  const u = me.user
  const depts = useQuery({ queryKey: ['departments'], queryFn: () => api<Department[]>('directory/departments'), staleTime: 60_000 })
  const { save, status } = useSaveProfile(me)
  const [editing, setEditing] = useState(false)
  const [first, setFirst] = useState(u.first_name)
  const [last, setLast] = useState(u.last_name)
  const [email, setEmail] = useState(u.email ?? '')
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    await save({ first_name: first.trim(), last_name: last.trim(), email: email || null })
    setEditing(false)
  }
  return (
    <div className="tag">
      <span className="att tape washi-mint wide" aria-hidden />
      <span className="avatar big" style={{ background: u.avatar_color }} aria-hidden>{initials(u.display_name)}</span>
      {editing ? (
        <form className="aform" onSubmit={submit}>
          <div className="field"><label htmlFor="p-first">{t('admin.firstName')}</label><input id="p-first" required value={first} onChange={(e) => setFirst(e.target.value)} /></div>
          <div className="field"><label htmlFor="p-last">{t('admin.lastName')}</label><input id="p-last" required value={last} onChange={(e) => setLast(e.target.value)} /></div>
          <div className="field"><label htmlFor="p-email">{t('profile.email')}</label><input id="p-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <div className="actions"><button className="btn primary">{t('common.save')}</button><button type="button" className="btn" onClick={() => setEditing(false)}>{t('common.cancel')}</button></div>
        </form>
      ) : (
        <>
          <h1>{u.display_name}</h1>
          <dl>
            <dt>{t('profile.role')}</dt><dd>{t(`role.${u.role}`)}{u.is_admin ? ` · ${t('admin.admin').toLowerCase()}` : ''}</dd>
            {me.mode === 'team' && <><dt>{t('admin.department')}</dt><dd>{depts.data?.find((d) => d.id === u.department_id)?.name ?? t('admin.noDepartment')}</dd></>}
            <dt>{t('admin.login')}</dt><dd>{u.login}</dd>
            <dt>{t('profile.email')}</dt><dd>{u.email || t('profile.noEmail')}</dd>
          </dl>
          <button className="btn small-btn" type="button" onClick={() => setEditing(true)}>{t('profile.editName')}</button>
        </>
      )}
      {status && <p className={status.ok ? 'notice' : 'error'}>{status.text}</p>}
    </div>
  )
}

function Section({ id, title, hint, children }: { id: string; title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="psec" aria-labelledby={id}>
      <div><h2 id={id}>{title}</h2>{hint && <p className="hint">{hint}</p>}</div>
      <div className="pbody">{children}</div>
    </section>
  )
}

function Password() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [pw, setPw] = useState({ old_password: '', new_password: '' })
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await api('auth/password', { body: pw })
      setPw({ old_password: '', new_password: '' })
      setOpen(false)
      setMsg({ ok: true, text: t('profile.changed') })
    } catch (x) {
      setMsg({ ok: false, text: errorText(t, x) })
    }
  }
  return (
    <div className="pline">
      <div className="w"><b>{t('profile.passwordTitle')}</b><small>{t('password.hint')}</small></div>
      {!open && <button className="btn" type="button" onClick={() => { setOpen(true); setMsg(null) }}>{t('profile.change')}</button>}
      {open && (
        <form className="aform full" onSubmit={submit}>
          <div className="row2">
            <div className="field"><label htmlFor="pw-old">{t('profile.oldPassword')}</label><input id="pw-old" required type="password" autoComplete="current-password" value={pw.old_password} onChange={(e) => setPw({ ...pw, old_password: e.target.value })} /></div>
            <div className="field"><label htmlFor="pw-new">{t('profile.newPassword')}</label><input id="pw-new" required type="password" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></div>
          </div>
          <div className="actions"><button className="btn primary">{t('profile.change')}</button><button type="button" className="btn" onClick={() => setOpen(false)}>{t('common.cancel')}</button></div>
        </form>
      )}
      {msg && <p className={`full ${msg.ok ? 'notice' : 'error'}`}>{msg.text}</p>}
    </div>
  )
}

function TwoFactor({ me }: { me: Me }) {
  const { t } = useTranslation()
  const setMe = useSetMe()
  const u = me.user
  const [setup, setSetup] = useState<{ secret: string; uri: string } | null>(null)
  const [disabling, setDisabling] = useState(false)
  const [code, setCode] = useState('')
  const [err, setErr] = useState('')
  const start = async () => {
    setErr('')
    try { setSetup(await api('auth/totp/setup', { method: 'POST' })) } catch (x) { setErr(errorText(t, x)) }
  }
  const confirm = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    try {
      setMe(await api<Me>(u.totp_enabled ? 'auth/totp/disable' : 'auth/totp/enable', { body: { code } }))
      setSetup(null)
      setDisabling(false)
      setCode('')
    } catch (x) {
      setErr(errorText(t, x))
    }
  }
  const asking = setup || disabling
  return (
    <div className="pline">
      <div className="w"><b>{t('profile.twofaTitle')}</b><small>{u.needs_2fa ? t('profile.twofaMandatory') : t('profile.twofaApps')}</small></div>
      <span className="state"><span className={`dot ${u.totp_enabled ? 'ok' : ''}`} aria-hidden />{u.totp_enabled ? t('profile.twofaOn') : t('profile.twofaOff')}</span>
      {!asking && !u.totp_enabled && <button className="btn" type="button" onClick={start}>{t('profile.enable2fa')}</button>}
      {!asking && u.totp_enabled && !u.needs_2fa && <button className="btn" type="button" onClick={() => setDisabling(true)}>{t('profile.disable2fa')}</button>}
      {asking && (
        <form className="aform full" onSubmit={confirm}>
          {setup && (
            <div className="qrrow">
              <div className="qr"><QRCodeSVG value={setup.uri} size={148} /></div>
              <p className="hint">{t('totp.setupLead')}<br /><span className="secret">{setup.secret}</span></p>
            </div>
          )}
          <div className="actions">
            <input className="code" required inputMode="numeric" autoComplete="one-time-code" placeholder={t('totp.code')} aria-label={t('totp.code')} value={code} onChange={(e) => setCode(e.target.value)} />
            <button className="btn primary">{setup ? t('totp.enable') : t('profile.disable2fa')}</button>
            <button type="button" className="btn" onClick={() => { setSetup(null); setDisabling(false) }}>{t('common.cancel')}</button>
          </div>
        </form>
      )}
      {err && <p className="full error">{err}</p>}
    </div>
  )
}

function PushRow() {
  const { t } = useTranslation()
  const [state, setState] = useState<PushState | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const refresh = () => pushState().then(setState)
  useEffect(() => { refresh() }, [])
  const run = async (fn: () => Promise<unknown>, okText?: string) => {
    setBusy(true)
    setMsg(null)
    try {
      await fn()
      if (okText) setMsg({ ok: true, text: okText })
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error && e.message === 'denied' ? t('profile.notify.state.denied') : errorText(t, e) })
    } finally {
      setBusy(false)
      refresh()
    }
  }
  const test = () => run(async () => {
    const r = await api<{ sent: boolean }>('push/test', { method: 'POST' })
    if (!r.sent) throw new Error(t('profile.notify.testFail'))
  }, t('profile.notify.testSent'))
  if (!state) return null
  const usable = state === 'on' || state === 'off'
  return (
    <div className="pline">
      <div className="w"><b>{t('profile.notify.push')}</b><small>{t(`profile.notify.state.${state}`)}</small></div>
      {usable && <span className="state"><span className={`dot ${state === 'on' ? 'ok' : ''}`} aria-hidden />{t(state === 'on' ? 'profile.twofaOn' : 'profile.twofaOff')}</span>}
      {state === 'off' && <button className="btn primary" type="button" disabled={busy} onClick={() => run(enablePush, t('profile.notify.enabled'))}>{t('profile.notify.enable')}</button>}
      {state === 'on' && <button className="btn" type="button" disabled={busy} onClick={test}>{t('profile.notify.test')}</button>}
      {state === 'on' && <button className="btn" type="button" disabled={busy} onClick={() => run(disablePush)}>{t('profile.notify.disable')}</button>}
      {msg && <p className={`full ${msg.ok ? 'notice' : 'error'}`}>{msg.text}</p>}
    </div>
  )
}

function Switch({ on, label, onChange }: { on: boolean; label: string; onChange: (v: boolean) => void }) {
  return <button type="button" role="switch" aria-checked={on} aria-label={label} className={`switch ${on ? 'on' : ''}`} onClick={() => onChange(!on)} />
}

function TelegramRow({ me, save }: { me: Me; save: (p: Partial<User>) => Promise<void> }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const setMe = useSetMe()
  const u = me.user
  const st = useQuery({ queryKey: ['tgstatus'], queryFn: () => api<{ configured: boolean; username: string | null }>('telegram/status') })
  const [link, setLink] = useState<{ url: string; username: string } | null>(null)
  const [err, setErr] = useState('')
  // while waiting for "Start" in the bot, poll the account so the row flips to "linked" by itself
  useEffect(() => {
    if (!link || u.telegram_linked) return
    const id = setInterval(() => qc.invalidateQueries({ queryKey: ['me'] }), 3000)
    const stop = setTimeout(() => clearInterval(id), 15 * 60_000)
    return () => { clearInterval(id); clearTimeout(stop) }
  }, [link, u.telegram_linked, qc])
  const start = async () => {
    setErr('')
    try {
      const r = await api<{ url: string; username: string }>('telegram/link', { method: 'POST' })
      setLink(r)
      window.open(r.url, '_blank', 'noopener')
    } catch (e) {
      setErr(errorText(t, e))
    }
  }
  const unlink = async () => {
    const user = await api<User>('telegram/link', { method: 'DELETE' })
    setMe({ ...me, user })
    setLink(null)
  }
  if (!st.data) return null
  return (
    <div className="pline">
      <div className="w">
        <b>Telegram</b>
        <small>
          {!st.data.configured ? t('profile.tg.noBot')
            : u.telegram_linked ? t('profile.tg.linked', { name: u.telegram_username ? `@${u.telegram_username}` : '' })
              : link ? <>{t('profile.tg.waiting')} <a href={link.url} target="_blank" rel="noreferrer">@{link.username}</a></>
                : t('profile.tg.hint')}
        </small>
      </div>
      {st.data.configured && !u.telegram_linked && <button className="btn primary" type="button" onClick={start}>{link ? t('profile.tg.again') : t('profile.tg.link')}</button>}
      {u.telegram_linked && <Switch on={u.notify_telegram} label={t('profile.tg.notify')} onChange={(v) => save({ notify_telegram: v })} />}
      {u.telegram_linked && <button className="btn" type="button" onClick={unlink}>{t('profile.tg.unlink')}</button>}
      {err && <p className="full error">{err}</p>}
    </div>
  )
}

const DAYS = ['1', '2', '3', '4', '5', '6', '7']

function Digest({ me, save }: { me: Me; save: (p: Partial<User>) => Promise<void> }) {
  const { t, i18n } = useTranslation()
  const u = me.user
  const names = weekdays(i18n.language)
  const toggleDay = (d: string) => {
    const set = new Set(u.digest_days)
    if (set.has(d)) set.delete(d)
    else set.add(d)
    save({ digest_days: DAYS.filter((x) => set.has(x)).join('') })
  }
  return (
    <>
      <div className="pline">
        <Switch on={u.digest_morning} label={t('profile.digest.morning')} onChange={(v) => save({ digest_morning: v })} />
        <div className="w"><b>{t('profile.digest.morning')}</b><small>{t('profile.digest.morningHint')}</small></div>
        {u.digest_morning && (
          <>
            <label htmlFor="dg-time" className="sr">{t('profile.digest.time')}</label>
            <input id="dg-time" className="time" type="time" step={900} value={u.digest_time} onChange={(e) => e.target.value && save({ digest_time: e.target.value })} />
          </>
        )}
      </div>
      {u.digest_morning && (
        <div className="digest-more">
          <div className="days" role="group" aria-label={t('profile.digest.days')}>
            {DAYS.map((d, i) => (
              <button key={d} type="button" className={`day ${u.digest_days.includes(d) ? 'on' : ''}`} aria-pressed={u.digest_days.includes(d)} onClick={() => toggleDay(d)}>{names[i]}</button>
            ))}
          </div>
          <label className="check"><input type="checkbox" checked={u.digest_skip_empty} onChange={(e) => save({ digest_skip_empty: e.target.checked })} />{t('profile.digest.skipEmpty')}</label>
        </div>
      )}
      <div className="pline">
        <Switch on={u.digest_evening} label={t('profile.digest.evening')} onChange={(v) => save({ digest_evening: v })} />
        <div className="w"><b>{t('profile.digest.evening')}</b><small>{t('profile.digest.eveningHint')}</small></div>
      </div>
    </>
  )
}

function Absence({ me, save }: { me: Me; save: (p: Partial<User>) => Promise<void> }) {
  const { t, i18n } = useTranslation()
  const u = me.user
  const people = useDirectory()
  const others = (people.data ?? []).filter((p) => p.id !== u.id)
  const today = isoDate(new Date())
  const awayNow = !!u.away_until && u.away_until >= today && (!u.away_from || u.away_from <= today)
  const planned = !!u.away_until && u.away_until >= today && !awayNow
  const deputy = others.find((p) => p.id === u.deputy_id)
  return (
    <>
      <div className="pline">
        <div className="w">
          <b>{awayNow ? t('profile.away.now', { date: shortDate(u.away_until!, i18n.language) })
            : planned ? t('profile.away.planned', { from: shortDate(u.away_from!, i18n.language), to: shortDate(u.away_until!, i18n.language) })
              : t('profile.away.atWork')}</b>
          <small>{deputy ? t('profile.away.deputyGets', { name: deputy.display_name }) : t('profile.away.noDeputy')}</small>
        </div>
        {(awayNow || planned) && <button className="btn" type="button" onClick={() => save({ away_from: null, away_until: null })}>{t('profile.away.back')}</button>}
      </div>
      <div className="row absence">
        <div className="field">
          <label htmlFor="aw-from">{t('profile.away.from')}</label>
          <input id="aw-from" type="date" value={u.away_from ?? ''} max={u.away_until ?? undefined} onChange={(e) => save({ away_from: e.target.value || null })} />
        </div>
        <div className="field">
          <label htmlFor="aw-until">{t('profile.away.until')}</label>
          <input id="aw-until" type="date" value={u.away_until ?? ''} min={u.away_from ?? today} onChange={(e) => save({ away_until: e.target.value || null })} />
        </div>
        <div className="field">
          <label htmlFor="aw-deputy">{t('profile.away.deputy')}</label>
          <select id="aw-deputy" value={u.deputy_id ?? ''} onChange={(e) => save({ deputy_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">{t('profile.away.nobody')}</option>
            {others.map((p) => <option key={p.id} value={p.id}>{p.display_name}</option>)}
          </select>
        </div>
      </div>
    </>
  )
}

function CalendarFeed() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const feed = useQuery({ queryKey: ['calendar'], queryFn: () => api<{ url: string | null }>('profile/calendar') })
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [renewing, setRenewing] = useState(false)
  const run = async (method: 'POST' | 'DELETE') => {
    setMsg(null)
    try {
      qc.setQueryData(['calendar'], await api<{ url: string | null }>('profile/calendar', { method }))
      setRenewing(false)
    } catch (e) {
      setMsg({ ok: false, text: errorText(t, e) })
    }
  }
  const copy = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url)
      setMsg({ ok: true, text: t('profile.cal.copied') })
    } catch {
      setMsg({ ok: false, text: t('profile.cal.copyFail') })
    }
  }
  if (!feed.data) return null
  const url = feed.data.url
  return (
    <div className="pline">
      <div className="w"><b>{t('profile.cal.title')}</b><small>{url ? t('profile.cal.on') : t('profile.cal.off')}</small></div>
      {!url && <button className="btn primary" type="button" onClick={() => run('POST')}>{t('profile.cal.enable')}</button>}
      {url && (
        <>
          <a className="btn" href={url.replace(/^https?:/, 'webcal:')}>{t('profile.cal.open')}</a>
          <button className="btn" type="button" onClick={() => run('DELETE')}>{t('profile.notify.disable')}</button>
          <div className="full calurl">
            <input readOnly value={url} aria-label={t('profile.cal.title')} onFocus={(e) => e.target.select()} />
            <button className="btn" type="button" onClick={() => copy(url)}>{t('profile.cal.copy')}</button>
          </div>
          <p className="full hint">{t('profile.cal.how')}</p>
          {!renewing
            ? <button className="linkish full" type="button" onClick={() => setRenewing(true)}>{t('profile.cal.renew')}</button>
            : (
              <p className="full hint">
                {t('profile.cal.renewWarn')}{' '}
                <button className="btn" type="button" onClick={() => run('POST')}>{t('profile.cal.renewYes')}</button>{' '}
                <button className="btn" type="button" onClick={() => setRenewing(false)}>{t('common.cancel')}</button>
              </p>
            )}
        </>
      )}
      {msg && <p className={`full ${msg.ok ? 'notice' : 'error'}`}>{msg.text}</p>}
    </div>
  )
}

export default function ProfilePage({ me }: { me: Me }) {
  const { t, i18n } = useTranslation()
  const u = me.user
  const { save, status } = useSaveProfile(me)
  const solo = useSolo()
  const zones = useMemo(() => {
    const list = ZONES.includes(u.timezone) ? ZONES : [u.timezone, ...ZONES]
    return list.map((z) => ({ z, label: zoneLabel(z, i18n.language) }))
  }, [u.timezone, i18n.language])
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000)
    return () => clearInterval(id)
  }, [])
  const time = new Intl.DateTimeFormat(intlLang(i18n.language), { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: u.timezone }).format(now)

  return (
    <div className="profile">
      <div className="tagcol">
        <NameTag me={me} />
        <p className="auto">{status ? <span className={status.ok ? 'notice' : 'error'}>{status.text}</span> : t('profile.autosave')}</p>
        <a className="guide-card" href={`guide/${i18n.language}/`} target="_blank" rel="noreferrer">
          <span className="gi" aria-hidden>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z" /><path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5" /><path d="M9 8h7M9 11.5h5" /></svg>
          </span>
          <span><b>{t('profile.guide')}</b><small>{t('profile.guideHint')}</small></span>
          <svg className="arr" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M7 17 17 7M9 7h8v8" /></svg>
        </a>
      </div>
      <div className="psecs">
        <Section id="p-look" title={t('profile.look')}>
          <div className="themes" role="radiogroup" aria-label={t('profile.theme')}>
            {(['light', 'dark', 'system'] as const).map((k) => (
              <button key={k} type="button" role="radio" aria-checked={u.theme === k} className={`th ${u.theme === k ? 'on' : ''}`} onClick={() => save({ theme: k })}>
                <span className="mini" style={{ background: THEME_PREVIEW[k].bg }}>{THEME_PREVIEW[k].tones.map((c) => <i key={c} style={{ background: c }} />)}</span>
                {t(`profile.themes.${k}`)}
              </button>
            ))}
          </div>
          <div className="row">
            <span className="rl">{t('profile.language')}</span>
            <select id="lang" aria-label={t('profile.language')} value={u.locale} onChange={(e) => save({ locale: e.target.value as Lang })}>
              {LANGS.map((l) => <option key={l.code} value={l.code} lang={l.code}>{l.name}</option>)}
            </select>
          </div>
        </Section>
        <Section id="p-time" title={t('profile.timeTitle')} hint={t('profile.timeHint')}>
          <div className="row">
            <label htmlFor="tz" className="sr">{t('profile.timezone')}</label>
            <select id="tz" value={u.timezone} onChange={(e) => save({ timezone: e.target.value })}>
              {zones.map(({ z, label }) => <option key={z} value={z}>{label}</option>)}
            </select>
            <span className="muted">{t('profile.nowAt', { time })}</span>
          </div>
        </Section>
        <Section id="p-notify" title={t('profile.notify.title')} hint={t('profile.notify.hint')}>
          <PushRow />
          <TelegramRow me={me} save={save} />
        </Section>
        {!solo && (
          <Section id="p-away" title={t('profile.away.title')} hint={t('profile.away.hint')}>
            <Absence me={me} save={save} />
          </Section>
        )}
        <Section id="p-cal" title={t('profile.cal.section')} hint={t('profile.cal.hint')}>
          <CalendarFeed />
        </Section>
        <Section id="p-digest" title={t('profile.digest.title')} hint={t('profile.digest.hint')}>
          <Digest me={me} save={save} />
        </Section>
        <Section id="p-sec" title={t('profile.security')}>
          <Password />
          <TwoFactor me={me} />
        </Section>
      </div>
    </div>
  )
}
