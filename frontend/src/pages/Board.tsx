import {
  DndContext, DragOverlay, KeyboardSensor, PointerSensor, TouchSensor, useDroppable, useSensor, useSensors,
  type DragEndEvent, type DragStartEvent,
} from '@dnd-kit/core'
import { useQuery } from '@tanstack/react-query'
import { memo, useCallback, useMemo, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type User } from '../api'
import { DraggableSticker, StickerFace, toneOf } from '../components/StickerCard'
import StickerSheet from '../components/StickerSheet'
import Compose from '../components/Compose'
import { QUADRANTS, useBoard, useMove, type Quadrant, type StickerSummary } from '../stickers'

type Period = 'morning' | 'day' | 'evening' | 'night'

function partOfDay(h: number): Period {
  if (h >= 5 && h < 12) return 'morning'
  if (h >= 12 && h < 18) return 'day'
  if (h >= 18 && h < 23) return 'evening'
  return 'night'
}

const SKY: Record<Period, ReactNode> = {
  morning: <><circle cx="12" cy="15" r="4" /><path d="M3 19h18M12 4v3M5.6 8.6l1.8 1.8M18.4 8.6l-1.8 1.8" /></>,
  day: <><circle cx="12" cy="12" r="4.2" /><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" /></>,
  evening: <><path d="M3 18h18M6 18a6 6 0 0 1 12 0" /><path d="M12 6v3M4.6 10.6l1.8 1.4M19.4 10.6 17.6 12" /></>,
  night: <path d="M19 14.5A7.5 7.5 0 0 1 9.5 5a7.5 7.5 0 1 0 9.5 9.5z" />,
}

const QICON: Record<Quadrant, ReactNode> = {
  do: <path d="M13 3 5 13.5h6L10 21l8-10.5h-6z" />,
  plan: <><rect x="4" y="5" width="16" height="15" rx="2.5" /><path d="M4 10h16M9 3v4M15 3v4" /></>,
  delegate: <><circle cx="8" cy="8" r="3" /><path d="M3 19c0-3 2.2-5 5-5s5 2 5 5M15 9h6M18 6l3 3-3 3" /></>,
  drop: <><path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13" /></>,
}

function Ring({ done, total }: { done: number; total: number }) {
  const { t } = useTranslation()
  const c = 2 * Math.PI * 21
  const v = total ? (done / total) * c : c
  return (
    <div className="ring">
      <svg width="52" height="52" viewBox="0 0 52 52" aria-hidden>
        <circle className="ring-bg" cx="26" cy="26" r="21" fill="none" strokeWidth="5" />
        <circle className="ring-v" cx="26" cy="26" r="21" fill="none" strokeWidth="5" strokeLinecap="round"
          strokeDasharray={`${v} ${c}`} transform="rotate(-90 26 26)" />
      </svg>
      <span><b>{t('board.ring', { done, total })}</b><small>{t('board.ringSub')}</small></span>
    </div>
  )
}

const Zone = memo(function Zone({ q, items, onOpen, dragging }: { q: Quadrant; items: StickerSummary[]; onOpen: (id: number) => void; dragging: boolean }) {
  const { t } = useTranslation()
  const { setNodeRef, isOver } = useDroppable({ id: q })
  const [expanded, setExpanded] = useState(false)
  const compact = items.length > 4
  const cut = !expanded && items.length > 8
  const shown = cut ? items.slice(0, 7) : items
  const n = { do: 1, plan: 2, delegate: 3, drop: 4 }[q]
  return (
    <section ref={setNodeRef} className={`zone p-q${n} ${toneOf(q)} ${compact ? 'compact' : ''} ${isOver ? 'over' : ''}`} aria-label={t(`quadrant.${q}`)}>
      <span className="num" aria-hidden>{n}</span>
      <div className="sec">
        <span className="qicon" aria-hidden>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{QICON[q]}</svg>
        </span>
        <div className="zt"><h2>{t(`quadrant.${q}`)}</h2><div className="verb">{t(`quadrant.verb.${q}`)}</div></div>
        <span className="spacer" />
        <span className="count">{items.length}</span>
      </div>
      <div className="stickers">
        {shown.map((s) => <DraggableSticker key={s.id} s={s} where="board" onOpen={onOpen} />)}
        {cut && (
          <button type="button" className="more" onClick={() => setExpanded(true)}>
            <b>+{items.length - 7}</b><span>{t('board.more')}</span>
          </button>
        )}
        {expanded && items.length > 8 && (
          <button type="button" className="collapse" onClick={() => setExpanded(false)}>{t('board.collapse')}</button>
        )}
        {isOver && dragging && <span className="slot" aria-hidden />}
        {!items.length && !isOver && <p className="zempty">{t('board.zoneEmpty')}</p>}
      </div>
    </section>
  )
})

/** overdue first, then by deadline, then newest */
function order(a: StickerSummary, b: StickerSummary) {
  if (a.overdue !== b.overdue) return a.overdue ? -1 : 1
  if (a.deadline !== b.deadline) return !a.deadline ? 1 : !b.deadline ? -1 : a.deadline.localeCompare(b.deadline)
  return b.id - a.id
}

export default function BoardPage({ user }: { user: User }) {
  const { t } = useTranslation()
  const board = useBoard()
  const sent = useQuery({ queryKey: ['sent'], queryFn: () => api<StickerSummary[]>('stickers/sent') })
  const move = useMove()
  const [params, setParams] = useSearchParams()
  const openId = params.get('s') ? Number(params.get('s')) : null
  const open = (id: number | null) => setParams(id ? { s: String(id) } : {}, { replace: false })
  // one stable callback for every sticker: setParams changes identity on each URL change
  const openRef = useRef(open)
  openRef.current = open
  const openSticker = useCallback((id: number) => openRef.current(id), [])
  const [compose, setCompose] = useState(false)
  const [query, setQuery] = useState('')
  const [dragId, setDragId] = useState<number | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 220, tolerance: 8 } }),
    useSensor(KeyboardSensor),
  )

  const all = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = board.data ?? []
    return q ? list.filter((s) => `${s.title} ${s.body} №${s.id}`.toLowerCase().includes(q)) : list
  }, [board.data, query])
  // memoized so that starting a drag (dragId changes) does not hand every zone a new array
  const inbox = useMemo(() => all.filter((s) => s.my_quadrant === null).sort(order), [all])
  const byQ = useMemo(
    () => Object.fromEntries(QUADRANTS.map((q) => [q, all.filter((s) => s.my_quadrant === q).sort(order)])) as Record<Quadrant, StickerSummary[]>,
    [all],
  )
  const total = board.data?.length ?? 0
  const triaged = (board.data ?? []).filter((s) => s.my_quadrant !== null).length
  const overdue = (board.data ?? []).filter((s) => s.overdue).length
  const waitingMe = (sent.data ?? []).filter((s) => s.status === 'needs_info').length
  const dragged = dragId !== null ? board.data?.find((s) => s.id === dragId) : undefined

  const hour = Number(new Intl.DateTimeFormat('en-GB', { hour: 'numeric', hourCycle: 'h23', timeZone: user.timezone }).format(new Date()))
  const period = partOfDay(hour)

  const onDragStart = (e: DragStartEvent) => setDragId(Number(e.active.id))
  const onDragEnd = (e: DragEndEvent) => {
    setDragId(null)
    const id = Number(e.active.id)
    const target = e.over?.id as Quadrant | undefined
    const s = board.data?.find((x) => x.id === id)
    if (s && target && QUADRANTS.includes(target) && s.my_quadrant !== target) move.mutate({ id, quadrant: target })
  }

  return (
    <div className={`board p-${period}`}>
      <div className="head">
        <div className="greet">
          <span className="sky" aria-hidden>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{SKY[period]}</svg>
          </span>
          <div>
            <h1>{t(`board.hello.${period}`)}, {user.first_name || user.display_name.split(' ')[0]}</h1>
            <p>{t(`board.lead.${period}`)}</p>
          </div>
        </div>
        {total > 0 && <Ring done={triaged} total={total} />}
        <span className="spacer" />
        <label className="search">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden><circle cx="11" cy="11" r="6.5" /><path d="M16 16l4.5 4.5" /></svg>
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('board.search')} aria-label={t('board.search')} />
        </label>
        <button className="create" type="button" onClick={() => setCompose(true)}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden><path d="M12 5v14M5 12h14" /></svg>
          {t('board.create')}
        </button>
      </div>

      <div className="kpis">
        <div className="kpi"><small>{t('board.kpi.inbox')}</small><b>{inbox.length}</b><em>{t('board.kpi.inboxNote')}</em></div>
        <div className="kpi"><small>{t('quadrant.do')}</small><b>{byQ.do.length}</b><em>{t('board.kpi.doNote')}</em></div>
        <div className="kpi"><small>{t('board.kpi.overdue')}</small><b className={overdue ? 'late' : ''}>{overdue}</b><em>{t('board.kpi.overdueNote')}</em></div>
        <Link to="/sent" className="kpi link"><small>{t('board.kpi.waitingMe')}</small><b className={waitingMe ? 'late' : ''}>{waitingMe}</b><em>{t('board.kpi.waitingMeNote')}</em></Link>
      </div>

      <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd} onDragCancel={() => setDragId(null)}>
        <section className="tray" aria-label={t('board.inbox')}>
          <div className="sec">
            <h2>{t('board.inbox')}</h2>
            <span className="count">{inbox.length}</span>
            <span className="m">{t('board.inboxHint')}</span>
          </div>
          <div className="pile">
            {inbox.map((s) => <DraggableSticker key={s.id} s={s} where="inbox" onOpen={openSticker} />)}
            {!inbox.length && (
              <p className="empty done">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
                {t('board.inboxEmpty')}
              </p>
            )}
          </div>
        </section>

        <section className="matrix" aria-label={t('board.matrix')}>
          <div className="ax a-tu" aria-hidden>{t('board.axis.urgent')}</div>
          <div className="ax a-tn" aria-hidden>{t('board.axis.notUrgent')}</div>
          <div className="ax v a-li" aria-hidden>{t('board.axis.important')}</div>
          <div className="ax v a-ln" aria-hidden>{t('board.axis.notImportant')}</div>
          {QUADRANTS.map((q) => <Zone key={q} q={q} items={byQ[q]} onOpen={openSticker} dragging={dragId !== null} />)}
        </section>

        <DragOverlay dropAnimation={{ duration: 260, easing: 'cubic-bezier(.2,1.3,.35,1)' }}>
          {dragged ? <StickerFace s={dragged} where={dragged.my_quadrant ? 'board' : 'inbox'} overlay /> : null}
        </DragOverlay>
      </DndContext>

      {openId !== null && <StickerSheet id={openId} onClose={() => open(null)} />}
      {compose && <Compose user={user} onClose={() => setCompose(false)} onCreated={(id) => { setCompose(false); open(id) }} />}
    </div>
  )
}
