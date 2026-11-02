import { useDraggable } from '@dnd-kit/core'
import { memo, useCallback, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { initials, looks, shortDate, shortName, type Quadrant, type StickerSummary } from '../stickers'

const TONE: Record<Quadrant, string> = { do: 'tone-q1', plan: 'tone-q2', delegate: 'tone-q3', drop: 'tone-q4' }

export function toneOf(q: Quadrant | null | undefined) {
  return q ? TONE[q] : 'tone-inbox'
}

export const PeopleIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
    <circle cx="9" cy="8" r="3.2" /><path d="M3 19c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5" /><circle cx="17" cy="9" r="2.6" /><path d="M16 13.6c2.9.1 5 2 5 4.9" />
  </svg>
)

/** Rubber stamp with the outcome of a finished sticker. */
export function Stamp({ s }: { s: StickerSummary }) {
  const { t } = useTranslation()
  if (s.status === 'withdrawn') return <span className="stamp mu">{t('status.withdrawn')}</span>
  if (s.status === 'rejected') return <span className="stamp no">{t('status.rejected')}</span>
  if (!s.outcome) return null
  return <span className={`stamp ${s.outcome === 'declined' ? 'no' : 'ok'}`}>{t(`outcome.${s.outcome}`)}</span>
}

/**
 * A small paper sticker.
 * where: inbox (author's estimate on top, white paper), board (my quadrant), list (Sent/Archive: recipient's decision).
 */
export const StickerFace = memo(function StickerFace({ s, where, onOpen, dragging, overlay, stamp, faded, extra }: {
  s: StickerSummary
  where: 'inbox' | 'board' | 'list'
  onOpen?: () => void
  dragging?: boolean
  overlay?: boolean
  stamp?: boolean
  faded?: boolean
  extra?: ReactNode
}) {
  const { t, i18n } = useTranslation()
  const lk = looks(s.id, s.overdue)
  const tone = where === 'inbox' ? 'tone-inbox' : toneOf(where === 'board' ? s.my_quadrant : s.decided_quadrant)
  const shown = where === 'board' ? s.my_quadrant : s.quadrant
  const diverge = where === 'board' && s.my_role === 'recipient' && s.kind === 'normal' && shown !== s.author_quadrant
  const cls = ['sticker', tone, lk.tilt, lk.jitter, dragging && 'dragging', overlay && 'lifted', faded && 'faded', stamp && 'stamped'].filter(Boolean).join(' ')
  // in Sent the interesting person is the recipient, elsewhere the author
  const person = where === 'list' && s.my_role === 'author' && s.recipients.length ? s.recipients[0] : s.author
  const from = s.kind === 'personal' ? t('sticker.forMe') : shortName(person.display_name)
  const top = where === 'inbox' ? t(`quadrant.short.${s.author_quadrant}`) : where === 'list' && faded ? `№${s.id}` : t(`status.${s.status}`)
  return (
    <button type="button" className={cls} onClick={onOpen} aria-label={`№${s.id} ${s.title}`}>
      <span className={`att ${lk.mount}`} aria-hidden />
      <span className="s-top">
        <span>{top}</span>
        {s.my_role === 'delegate' && <span title={t('sticker.delegatedToMe')}><PeopleIcon /></span>}
      </span>
      <span className="s-title">{s.title}</span>
      {diverge && <span className="s-div">{t('sticker.authorThought')}: {t(`quadrant.short.${s.author_quadrant}`)}</span>}
      {extra}
      {stamp && <Stamp s={s} />}
      <span className="s-foot">
        <span className="ava" style={{ background: person.avatar_color }} aria-hidden>{initials(person.display_name)}</span>
        <span className="s-from">{from}{s.recipients.length > 1 && where === 'list' ? ` +${s.recipients.length - 1}` : ''}</span>
        {s.deadline && !faded && <span className={s.overdue ? 'due late' : 'due'}>{shortDate(s.deadline, i18n.language)}</span>}
      </span>
    </button>
  )
})

/** onOpen gets the id, so the board can pass one stable callback and memo keeps idle stickers from re-rendering while one is dragged. */
export const DraggableSticker = memo(function DraggableSticker({ s, where, onOpen, disabled }: {
  s: StickerSummary
  where: 'inbox' | 'board'
  onOpen: (id: number) => void
  disabled?: boolean
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: s.id, disabled })
  const openThis = useCallback(() => onOpen(s.id), [onOpen, s.id])
  return (
    <div ref={setNodeRef} className="drag-wrap" {...listeners} {...attributes} role={undefined} tabIndex={-1}>
      <StickerFace s={s} where={where} onOpen={openThis} dragging={isDragging} />
    </div>
  )
})
