import { useQuery } from '@tanstack/react-query'
import { useMemo, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { api, type User } from '../api'
import Compose from '../components/Compose'
import { StickerFace, toneOf } from '../components/StickerCard'
import StickerSheet from '../components/StickerSheet'
import { errorText } from '../session'
import { monthYear } from '../dates'
import { dateTime, initials, useAction, useSticker, type StickerSummary } from '../stickers'

export function useOpenSticker() {
  const [params, setParams] = useSearchParams()
  const openId = params.get('s') ? Number(params.get('s')) : null
  const open = (id: number | null) => {
    const next = new URLSearchParams(params)
    if (id) next.set('s', String(id))
    else next.delete('s')
    setParams(next)
  }
  return [openId, open] as const
}

export const PlusIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden><path d="M12 5v14M5 12h14" /></svg>
)
const SearchIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden><circle cx="11" cy="11" r="6.5" /><path d="M16 16l4.5 4.5" /></svg>
)

/** A sticker pinned on top of Sent: the manager asked a question, the answer goes right here. */
function AskCard({ s }: { s: StickerSummary }) {
  const { t, i18n } = useTranslation()
  const detail = useSticker(s.id)
  const answer = useAction(s.id)
  const [text, setText] = useState('')
  const question = [...(detail.data?.thread ?? [])].reverse().find((c) => c.kind === 'question')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    answer.mutate({ action: 'answer', text })
  }
  const to = s.recipients[0]
  return (
    <section className="ask" aria-label={t('lists.needAnswer')}>
      <span className="att pin pin-red" aria-hidden />
      <div>
        <span className="kick">{t('lists.needAnswer')}</span>
        <h2>{s.title}</h2>
        {to && <div className="to">№{s.id} · <span className="ava" style={{ background: to.avatar_color }}>{initials(to.display_name)}</span>{to.display_name}</div>}
      </div>
      <form onSubmit={submit}>
        {question && (
          <div className="q">
            <span className="ava lg" style={{ background: question.author.avatar_color }} aria-hidden>{initials(question.author.display_name)}</span>
            <div className="bub"><small>{question.author.display_name} · {dateTime(question.created_at, i18n.language)}</small><p>{question.body}</p></div>
          </div>
        )}
        <div className="ans">
          <label htmlFor={`ans-${s.id}`} className="sr">{t('sheet.prompt.answer')}</label>
          <textarea id={`ans-${s.id}`} value={text} onChange={(e) => setText(e.target.value)} placeholder={t('lists.answerPh')} />
          <button className="btn primary" type="submit" disabled={!text.trim() || answer.isPending}>{t('action.answer')}</button>
        </div>
        {answer.isError && <p className="error">{errorText(t, answer.error)}</p>}
      </form>
    </section>
  )
}

function ResolvedSticker({ s, onOpen }: { s: StickerSummary; onOpen: () => void }) {
  const { t } = useTranslation()
  const confirm = useAction(s.id)
  return (
    <div className="with-btn">
      <StickerFace s={s} where="list" onOpen={onOpen} stamp />
      <button className="btn got" type="button" disabled={confirm.isPending} onClick={() => confirm.mutate({ action: 'confirm' })}>{t('lists.got')}</button>
    </div>
  )
}

function Lane({ title, hint, items, children }: { title: string; hint: string; items: number; children: React.ReactNode }) {
  return (
    <section className="lane" aria-label={title}>
      <div className="lh"><h2>{title}</h2><span>{hint}</span><b className="count">{items}</b></div>
      <div className="lane-stickers">{children}</div>
    </section>
  )
}

export function SentPage({ user }: { user: User }) {
  const { t } = useTranslation()
  const [all, setAll] = useState(false)
  const [compose, setCompose] = useState(false)
  const [openId, open] = useOpenSticker()
  const sent = useQuery({
    queryKey: ['sent', all],
    queryFn: () => api<StickerSummary[]>(`stickers/sent${all ? '?include_archived=true' : ''}`),
  })
  const shared = useQuery({ queryKey: ['shared'], queryFn: () => api<StickerSummary[]>('stickers/shared') })
  const list = sent.data ?? []
  const asks = list.filter((s) => s.status === 'needs_info')
  const waiting = list.filter((s) => s.status === 'new')
  const working = list.filter((s) => ['triaged', 'in_progress', 'delegated', 'snoozed'].includes(s.status))
  const resolved = list.filter((s) => s.status === 'resolved')
  const finished = list.filter((s) => ['closed', 'rejected', 'withdrawn'].includes(s.status))
  const face = (s: StickerSummary) => <StickerFace key={s.id} s={s} where="list" onOpen={() => open(s.id)} />

  return (
    <div className="page-wide">
      <div className="head">
        <h1>{t('nav.sent')}</h1>
        <div className="seg" role="group" aria-label={t('lists.filter')}>
          <button type="button" className={all ? '' : 'on'} aria-pressed={!all} onClick={() => setAll(false)}>{t('lists.active')}</button>
          <button type="button" className={all ? 'on' : ''} aria-pressed={all} onClick={() => setAll(true)}>{t('lists.all')}</button>
        </div>
        <span className="spacer" />
        <button className="create" type="button" onClick={() => setCompose(true)}><PlusIcon />{t('board.create')}</button>
      </div>

      {asks.map((s) => <AskCard key={s.id} s={s} />)}

      {sent.isSuccess && list.length === 0 ? (
        <div className="empty-desk"><p>{t('lists.sentEmpty')}</p><button className="btn" type="button" onClick={() => setCompose(true)}><PlusIcon />{t('board.create')}</button></div>
      ) : (
        <div className={`lanes ${all ? 'four' : ''}`}>
          <Lane title={t('lists.lane.waiting')} hint={t('lists.lane.waitingHint')} items={waiting.length}>{waiting.map(face)}</Lane>
          <Lane title={t('lists.lane.working')} hint={t('lists.lane.workingHint')} items={working.length}>{working.map(face)}</Lane>
          <Lane title={t('lists.lane.resolved')} hint={t('lists.lane.resolvedHint')} items={resolved.length}>
            {resolved.map((s) => <ResolvedSticker key={s.id} s={s} onOpen={() => open(s.id)} />)}
          </Lane>
          {all && (
            <Lane title={t('lists.lane.finished')} hint={t('lists.lane.finishedHint')} items={finished.length}>
              {finished.map((s) => <StickerFace key={s.id} s={s} where="list" onOpen={() => open(s.id)} stamp faded />)}
            </Lane>
          )}
        </div>
      )}

      {(shared.data?.length ?? 0) > 0 && (
        <section className="shared">
          <h2>{t('lists.shared')}</h2>
          <div className="lane-stickers">{shared.data!.map((s) => <StickerFace key={s.id} s={s} where="list" onOpen={() => open(s.id)} />)}</div>
        </section>
      )}

      {openId !== null && <StickerSheet id={openId} onClose={() => open(null)} />}
      {compose && <Compose user={user} onClose={() => setCompose(false)} onCreated={(id) => { setCompose(false); open(id) }} />}
    </div>
  )
}

type Filter = 'all' | 'done' | 'approved' | 'declined' | 'withdrawn'
const FILTERS: Filter[] = ['all', 'done', 'approved', 'declined', 'withdrawn']

function matches(s: StickerSummary, f: Filter) {
  switch (f) {
    case 'all': return true
    case 'done': return s.outcome === 'done' || s.outcome === 'fyi'
    case 'approved': return s.outcome === 'approved'
    case 'declined': return s.outcome === 'declined' || s.status === 'rejected'
    case 'withdrawn': return s.status === 'withdrawn'
  }
}

export function ArchivePage() {
  const { t, i18n } = useTranslation()
  const [q, setQ] = useState('')
  const [term, setTerm] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [opened, setOpened] = useState<Set<string>>(new Set())
  const [openId, open] = useOpenSticker()
  const list = useQuery({
    queryKey: ['archive', term],
    queryFn: () => api<StickerSummary[]>(`stickers/archive?limit=500&q=${encodeURIComponent(term)}`),
  })
  const months = useMemo(() => {
    const groups = new Map<string, StickerSummary[]>()
    for (const s of (list.data ?? []).filter((x) => matches(x, filter))) {
      const u = new Date(s.updated_at) // group by the viewer's local month, not UTC
      const k = `${u.getFullYear()}-${String(u.getMonth() + 1).padStart(2, '0')}`
      groups.set(k, [...(groups.get(k) ?? []), s])
    }
    return [...groups.entries()]
  }, [list.data, filter])
  const monthName = (k: string) => {
    return monthYear(k, i18n.language)
  }
  const searching = term.trim() !== '' || filter !== 'all'

  return (
    <div className="page-wide">
      <div className="head">
        <h1>{t('nav.archive')}</h1>
        <form className="search wide" onSubmit={(e) => { e.preventDefault(); setTerm(q) }} role="search">
          <SearchIcon />
          <input type="search" value={q} onChange={(e) => { setQ(e.target.value); if (!e.target.value) setTerm('') }} placeholder={t('lists.archiveSearch')} aria-label={t('lists.archiveSearch')} />
        </form>
      </div>
      <div className="chips" role="group" aria-label={t('sheet.outcome')}>
        {FILTERS.map((f) => (
          <button key={f} type="button" className={`tgl ${filter === f ? 'on' : ''}`} aria-pressed={filter === f} onClick={() => setFilter(f)}>{t(`lists.filters.${f}`)}</button>
        ))}
      </div>

      {list.isSuccess && months.length === 0 && <div className="empty-desk"><p>{searching ? t('lists.nothingFound') : t('lists.archiveEmpty')}</p></div>}

      {months.map(([k, items], i) => {
        const expanded = i === 0 || searching || opened.has(k)
        return (
          <section className="month" key={k} aria-label={monthName(k)}>
            <div className="mh"><h2>{monthName(k)}</h2><span>{t('lists.nStickers', { count: items.length })}</span></div>
            {expanded ? (
              <div className="lane-stickers">{items.map((s) => <StickerFace key={s.id} s={s} where="list" onOpen={() => open(s.id)} stamp faded />)}</div>
            ) : (
              <button type="button" className="pile-btn" onClick={() => setOpened(new Set(opened).add(k))} aria-label={t('lists.unfold', { month: monthName(k) })}>
                <span className="sheets" aria-hidden>
                  {items.slice(0, 3).map((s, j) => <i key={s.id} className={toneOf(s.decided_quadrant)} style={{ transform: `rotate(${[5, -4, 1.5][j]}deg) translate(${[12, 6, 0][j]}px, ${[5, 2, 0][j]}px)` }} />)}
                </span>
                <span><b>{items.length}</b><span>{t('lists.pileHint')}</span></span>
              </button>
            )}
          </section>
        )
      })}

      {openId !== null && <StickerSheet id={openId} onClose={() => open(null)} />}
    </div>
  )
}
