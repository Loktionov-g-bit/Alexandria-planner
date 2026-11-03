import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { initials, looks, shortDate, useMove, QUADRANTS, type Quadrant, type StickerSummary } from '../stickers'
import { toneOf } from './StickerCard'

/**
 * Inbox triage, one sticker at a time: keys 1–4 put it into a quadrant, Enter opens it,
 * → / Space skips, ← goes back, Esc leaves. The queue is fixed when the mode opens, so
 * stickers that arrive meanwhile do not shuffle the order under the user's fingers.
 */
export default function Triage({ inbox, paused, onOpen, onClose }: {
  inbox: StickerSummary[]
  paused: boolean // a sticker sheet is open on top: keys belong to it
  onOpen: (id: number) => void
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const move = useMove()
  const [queue] = useState(() => inbox.map((s) => s.id))
  const [pos, setPos] = useState(0)
  const [placed, setPlaced] = useState<Record<number, Quadrant>>({})
  const byId = useMemo(() => new Map(inbox.map((s) => [s.id, s])), [inbox])
  // the next sticker still waiting in the inbox (handled elsewhere = skipped quietly)
  const waiting = (from: number, step: 1 | -1) => {
    for (let i = from; i >= 0 && i < queue.length; i += step) if (byId.has(queue[i]) && !placed[queue[i]]) return i
    return -1
  }
  const cur = waiting(pos, 1)
  const s = cur >= 0 ? byId.get(queue[cur]) : undefined
  const done = Object.keys(placed).length

  const put = (q: Quadrant) => {
    if (!s) return
    move.mutate({ id: s.id, quadrant: q })
    setPlaced((p) => ({ ...p, [s.id]: q }))
    setPos(cur + 1)
  }
  const skip = () => s && setPos(cur + 1)
  const back = () => {
    const prev = waiting(cur >= 0 ? cur - 1 : queue.length - 1, -1)
    if (prev >= 0) setPos(prev)
  }

  useEffect(() => {
    if (paused) return
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return
      const n = Number(e.key)
      if (n >= 1 && n <= 4) put(QUADRANTS[n - 1])
      else if (e.key === 'Escape') onClose()
      else if (e.key === 'Enter' && s) onOpen(s.id)
      else if (e.key === 'ArrowRight' || e.key === ' ') skip()
      else if (e.key === 'ArrowLeft') back()
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const left = queue.filter((id) => byId.has(id) && !placed[id]).length
  const lk = s ? looks(s.id, s.overdue) : null
  return (
    <div className="scrim triage-scrim" onClick={onClose}>
      <div className="triage" role="dialog" aria-modal="true" aria-label={t('triage.title')} onClick={(e) => e.stopPropagation()}>
        <div className="tr-top">
          <b>{t('triage.title')}</b>
          <span className="muted">{s ? t('triage.left', { count: left }) : ''}</span>
          <button type="button" className="close" onClick={onClose} aria-label={t('common.close')}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>

        {s && lk ? (
          <>
            <div className="paperwrap tone-inbox" key={s.id}>
              <article className="paper tr-paper">
                <span className={`att ${lk.mount}`} aria-hidden />
                <p className="from">
                  <span className="ava" style={{ background: s.author.avatar_color }} aria-hidden>{initials(s.author.display_name)}</span>
                  <span>{s.author.display_name}<small>№{s.id} · {shortDate(s.created_at.slice(0, 10), i18n.language)}</small></span>
                </p>
                <h2>{s.title}</h2>
                {s.body && <p className="body">{s.body}</p>}
                <p className="tr-meta">
                  {s.kind === 'normal' && <span className="chip">{t('triage.thinks')}: {t(`quadrant.short.${s.author_quadrant}`)}</span>}
                  {s.deadline && <span className={`chip ${s.overdue ? 'late' : ''}`}>{t('sheet.due')} {shortDate(s.deadline, i18n.language)}</span>}
                  {(s.comments > 0 || s.attachments > 0) && <span className="chip">{t('triage.more', { comments: s.comments, files: s.attachments })}</span>}
                </p>
              </article>
            </div>
            <div className="tr-q">
              {QUADRANTS.map((q, i) => (
                <button key={q} type="button" className={`qbtn ${toneOf(q)} ${s.author_quadrant === q ? 'hint-q' : ''}`} onClick={() => put(q)}>
                  <kbd>{i + 1}</kbd>{t(`quadrant.${q}`)}
                </button>
              ))}
            </div>
            <div className="tr-nav">
              <button type="button" className="btn" onClick={back} disabled={waiting(cur - 1, -1) < 0}><kbd>←</kbd>{t('triage.back')}</button>
              <button type="button" className="btn" onClick={() => onOpen(s.id)}><kbd>Enter</kbd>{t('triage.open')}</button>
              <button type="button" className="btn" onClick={skip}>{t('triage.skip')}<kbd>→</kbd></button>
            </div>
          </>
        ) : (
          <div className="tr-done">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
            <h2>{left ? t('triage.endSkipped', { count: left }) : t('triage.done')}</h2>
            <p className="muted">{t('triage.sorted', { count: done })}</p>
            <div className="tr-nav">
              {left > 0 && <button type="button" className="btn" onClick={() => setPos(0)}>{t('triage.again')}</button>}
              <button type="button" className="btn primary" onClick={onClose}>{t('triage.finish')}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
