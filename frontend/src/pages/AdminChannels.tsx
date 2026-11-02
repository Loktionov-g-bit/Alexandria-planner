import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import { errorText } from '../session'
import { initials } from '../stickers'

type Ch = 'stable' | 'beta'
interface Overview {
  this: { channel: Ch; version: string }
  beta: { configured: boolean; reachable: boolean; version: string | null }
  departments: { id: number; name: string; channel: Ch | null }[]
  users: { id: number; display_name: string; avatar_color: string; department_id: number | null; channel: Ch | null; effective: Ch }[]
  on_beta: number
}

function Seg<T extends string | null>({ value, options, onPick, label }: { value: T; options: [T, string][]; onPick: (v: T) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(([v, text]) => (
        <button key={String(v)} type="button" className={value === v ? 'on' : ''} aria-pressed={value === v} onClick={() => onPick(v)}>{text}</button>
      ))}
    </div>
  )
}

/** Admin: canary rollout. Who sees the beta version; one-button rollout and rollback. */
export default function AdminChannels() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const ov = useQuery({ queryKey: ['admin', 'channels'], queryFn: () => api<Overview>('admin/channels') })
  const [err, setErr] = useState('')
  const run = async (fn: () => Promise<unknown>) => {
    setErr('')
    try {
      await fn()
    } catch (e) {
      setErr(errorText(t, e))
    }
    qc.invalidateQueries({ queryKey: ['admin', 'channels'] })
  }
  const d = ov.data
  if (!d) return null
  const betaState = !d.beta.configured ? 'off' : d.beta.reachable ? 'up' : 'down'
  return (
    <div className="channels">
      <div className="card stack">
        <div className="vers">
          <div><small>{t('ch.stable')}</small><b>{d.this.channel === 'stable' ? `v${d.this.version}` : '—'}</b></div>
          <div><small>{t('ch.beta')}</small><b>{d.beta.version ? `v${d.beta.version}` : '—'}</b>
            <span className="state"><span className={`dot ${betaState === 'up' ? 'ok' : ''}`} aria-hidden />{t(`ch.state.${betaState}`)}</span></div>
          <div><small>{t('ch.onBeta')}</small><b>{d.on_beta}</b></div>
        </div>
        <div className="actions">
          <button className="btn primary" type="button" disabled={betaState !== 'up'} onClick={() => run(() => api('admin/channels/all', { body: { channel: 'beta' } }))}>{t('ch.allBeta')}</button>
          <button className="btn" type="button" disabled={d.on_beta === 0} onClick={() => run(() => api('admin/channels/all', { body: { channel: 'stable' } }))}>{t('ch.allStable')}</button>
        </div>
        <p className="hint">{t(betaState === 'off' ? 'ch.hintOff' : 'ch.hint')}</p>
        {err && <p className="error">{err}</p>}
      </div>

      <section className="lane">
        <div className="lh"><h2>{t('admin.departments')}</h2></div>
        <ul className="chlist">
          {d.departments.map((dep) => (
            <li key={dep.id}>
              <span className="nm">{dep.name}</span>
              <Seg<Ch | null> value={dep.channel ?? 'stable'} label={dep.name} options={[['stable', 'stable'], ['beta', 'beta']]}
                onPick={(v) => run(() => api(`admin/channels/departments/${dep.id}`, { method: 'PUT', body: { channel: v === 'stable' ? null : v } }))} />
            </li>
          ))}
        </ul>
      </section>

      <section className="lane">
        <div className="lh"><h2>{t('admin.users')}</h2><span>{t('ch.usersHint')}</span></div>
        <ul className="chlist">
          {d.users.map((u) => (
            <li key={u.id}>
              <span className="nm"><span className="ava" style={{ background: u.avatar_color }} aria-hidden>{initials(u.display_name)}</span>{u.display_name}
                {u.effective === 'beta' && <span className="beta-badge">beta</span>}</span>
              <Seg<Ch | null> value={u.channel} label={u.display_name} options={[[null, t('ch.inherit')], ['stable', 'stable'], ['beta', 'beta']]}
                onPick={(v) => run(() => api(`admin/channels/users/${u.id}`, { method: 'PUT', body: { channel: v } }))} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
