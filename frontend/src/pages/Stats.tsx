import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import { toneOf } from '../components/StickerCard'
import { shortDate } from '../dates'
import { initials, isoDate, QUADRANTS, type Quadrant, type UserBrief } from '../stickers'

type Kind = 'day' | 'week' | 'month' | 'quarter' | 'custom'

interface Stats {
  scope: 'received' | 'sent'
  period: { start: string; end: string }
  totals: { total: number; resolved: number; active: number; overdue: number }
  times: { to_triage: number | null; to_resolve: number | null; to_close: number | null; total: number | null }
  divergence: { judged: number; diverged: number }
  board: Record<'inbox' | Quadrant, number>
  by_quadrant: Record<Quadrant, number>
  people: { user: UserBrief; sent: number; resolved: number; avg_response_hours: number | null; diverged: number; judged: number }[]
  e2e: { count: number; avg_response_hours: number | null } | null
}

function useDuration() {
  const { t } = useTranslation()
  return (h: number | null) => {
    if (h === null) return '—'
    if (h < 1) return t('stats.min', { n: Math.max(1, Math.round(h * 60)) })
    if (h < 48) return t('stats.hours', { n: Math.round(h * 10) / 10 })
    return t('stats.days', { n: Math.round((h / 24) * 10) / 10 })
  }
}

export default function StatsPage() {
  const { t, i18n } = useTranslation()
  const dur = useDuration()
  const [kind, setKind] = useState<Kind>('week')
  const [start, setStart] = useState(() => { const d = new Date(); d.setDate(d.getDate() - 13); return isoDate(d) })
  const [end, setEnd] = useState(() => isoDate(new Date()))
  const params = new URLSearchParams({ period: kind, ...(kind === 'custom' ? { start, end } : {}) }).toString()
  const q = useQuery({ queryKey: ['stats', params], queryFn: () => api<Stats>(`stats?${params}`) })
  const s = q.data
  const max = s ? Math.max(1, ...Object.values(s.board)) : 1
  const fmt = (iso: string) => shortDate(iso, i18n.language)

  return (
    <div className="page-wide stats">
      <div className="head">
        <h1>{t('nav.stats')}</h1>
        <div className="seg" role="group" aria-label={t('stats.period')}>
          {(['day', 'week', 'month', 'quarter', 'custom'] as Kind[]).map((k) => (
            <button key={k} type="button" className={kind === k ? 'on' : ''} aria-pressed={kind === k} onClick={() => setKind(k)}>{t(`stats.p.${k}`)}</button>
          ))}
        </div>
        {kind === 'custom' && (
          <div className="row">
            <input type="date" value={start} max={end} onChange={(e) => setStart(e.target.value)} aria-label={t('stats.from')} />
            <input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} aria-label={t('stats.to')} />
          </div>
        )}
        <span className="spacer" />
        <a className="btn" href={`api/stats/report.xlsx?${params}`} download>
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></svg>
          {t('stats.excel')}
        </a>
      </div>

      {s && (
        <>
          <p className="scope">{t(`stats.scope.${s.scope}`)} · {fmt(s.period.start)} — {fmt(s.period.end)}</p>
          <div className="kpis">
            <div className="kpi"><small>{t('stats.total')}</small><b>{s.totals.total}</b><em>{t('stats.totalNote')}</em></div>
            <div className="kpi"><small>{t('stats.resolved')}</small><b>{s.totals.resolved}</b><em>{t('stats.resolvedNote')}</em></div>
            <div className="kpi"><small>{t('stats.active')}</small><b>{s.totals.active}</b><em>{t('stats.activeNote')}</em></div>
            <div className="kpi"><small>{t('stats.overdue')}</small><b className={s.totals.overdue ? 'late' : ''}>{s.totals.overdue}</b><em>{t('stats.overdueNote')}</em></div>
          </div>

          <div className="stat-grid">
            <section className="lane" aria-labelledby="st-board">
              <div className="lh"><h2 id="st-board">{t('stats.board')}</h2><span>{t('stats.boardHint')}</span></div>
              <ul className="bars">
                {(['inbox', ...QUADRANTS] as const).map((k) => (
                  <li key={k}>
                    <span className="bl">{k === 'inbox' ? t('board.inbox') : t(`quadrant.${k}`)}</span>
                    <span className="bt"><i className={toneOf(k === 'inbox' ? null : k)} style={{ width: `${(s.board[k] / max) * 100}%` }} /></span>
                    <b>{s.board[k]}</b>
                  </li>
                ))}
              </ul>
            </section>
            <section className="lane" aria-labelledby="st-speed">
              <div className="lh"><h2 id="st-speed">{t('stats.speed')}</h2><span>{t('stats.speedHint')}</span></div>
              <dl className="speed">
                <div><dt>{t('stats.toTriage')}</dt><dd>{dur(s.times.to_triage)}</dd></div>
                <div><dt>{t('stats.toResolve')}</dt><dd>{dur(s.times.to_resolve)}</dd></div>
                <div><dt>{t('stats.toClose')}</dt><dd>{dur(s.times.to_close)}</dd></div>
              </dl>
              <p className="match">
                {s.divergence.judged
                  ? t('stats.match', { same: s.divergence.judged - s.divergence.diverged, all: s.divergence.judged })
                  : t('stats.noJudged')}
              </p>
            </section>
          </div>

          <section className="lane people" aria-labelledby="st-people">
            <div className="lh"><h2 id="st-people">{t(`stats.people.${s.scope}`)}</h2></div>
            {s.people.length === 0 ? <p className="muted">{t('stats.empty')}</p> : (
              <div className="table-wrap">
                <table className="table">
                  <thead><tr>
                    <th>{t(`stats.person.${s.scope}`)}</th><th>{t(`stats.count.${s.scope}`)}</th><th>{t('stats.resolved')}</th>
                    <th>{t('stats.response')}</th><th>{t('stats.mismatch')}</th>
                  </tr></thead>
                  <tbody>
                    {s.people.map((p) => (
                      <tr key={p.user.id}>
                        <td><span className="who"><span className="ava" style={{ background: p.user.avatar_color }} aria-hidden>{initials(p.user.display_name)}</span>{p.user.display_name}</span></td>
                        <td>{p.sent}</td><td>{p.resolved}</td><td>{dur(p.avg_response_hours)}</td>
                        <td>{p.judged ? `${p.diverged} / ${p.judged}` : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {s.e2e && s.e2e.count > 0 && <p className="hint">{t('stats.e2e', { count: s.e2e.count, time: dur(s.e2e.avg_response_hours) })}</p>}
          </section>
        </>
      )}
    </div>
  )
}
