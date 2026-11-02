import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import { errorText } from '../session'
import {
  QUADRANTS, addDays, dateTime, initials, looks, shortDate, uploadFile, useAction, useDirectory, useInvalidateStickers,
  useMove, useSticker, type Attachment, type Outcome, type StickerDetail, type Status,
} from '../stickers'
import { toneOf } from './StickerCard'

const STEPS: Status[] = ['new', 'triaged', 'in_progress', 'resolved', 'closed']
const STEP_OF: Record<Status, number> = {
  new: 0, withdrawn: 0, triaged: 1, snoozed: 1, rejected: 1, in_progress: 2, needs_info: 2, delegated: 2, resolved: 3, closed: 4,
}
const TERMINAL: Status[] = ['withdrawn', 'rejected']
// buttons in the order a manager usually needs them
const ORDER = ['start', 'resolve', 'ask', 'delegate', 'snooze', 'reject', 'rework', 'wake', 'answer', 'report', 'confirm', 'reopen', 'withdraw']
const NEEDS_TEXT = new Set(['ask', 'answer', 'report', 'rework', 'reject', 'reopen'])
const OUTCOMES: Outcome[] = ['approved', 'declined', 'done', 'fyi']

/** actions that need no input: run on click */
function isInstant(s: StickerDetail, a: string) {
  return ['start', 'confirm', 'withdraw', 'wake'].includes(a) || (a === 'resolve' && s.kind === 'personal')
}

export const FileIcon = () => (
  // a document sheet, never a paperclip
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" />
  </svg>
)

function Files({ files }: { files: Attachment[] }) {
  if (!files.length) return null
  return (
    <div className="files">
      {files.map((f) => (
        <a key={f.id} className="file" href={`api/attachments/${f.id}`} target="_blank" rel="noreferrer">
          <FileIcon />{f.filename}<small>{Math.max(1, Math.round(f.size / 1024))} KB</small>
        </a>
      ))}
    </div>
  )
}

function Steps({ status }: { status: Status }) {
  const { t } = useTranslation()
  const cur = STEP_OF[status]
  const steps = TERMINAL.includes(status) ? STEPS.slice(0, cur + 1) : STEPS
  return (
    <ol className="steps">
      {steps.map((st, i) => (
        <li key={st} className={`step ${i < cur ? 'done' : i === cur ? 'cur' : ''}`}>
          <i />{t(`status.${i === cur ? status : st}`)}
        </li>
      ))}
    </ol>
  )
}

function historyLine(h: StickerDetail['history'][number], t: (k: string, o?: Record<string, unknown>) => string) {
  const d = h.data as Record<string, string | boolean | null>
  switch (h.action) {
    case 'status': return t('history.status', { status: t(`status.${d.new}`) })
    case 'quadrant': return t('history.quadrant', { q: t(`quadrant.${d.new}`) })
    case 'deadline': return d.new ? t('history.deadline', { date: d.new }) : t('history.deadlineRemoved')
    default: return t(`history.${h.action}`)
  }
}

function ActionForm({ s, action, onDone }: { s: StickerDetail; action: string; onDone: () => void }) {
  const { t } = useTranslation()
  const run = useAction(s.id)
  const people = useDirectory()
  const [text, setText] = useState('')
  const [userId, setUserId] = useState<number | ''>('')
  const [outcome, setOutcome] = useState<Outcome | ''>('')
  const [until, setUntil] = useState(addDays(1))

  const submit = (e?: FormEvent) => {
    e?.preventDefault()
    run.mutate(
      {
        action,
        text: text.trim() || undefined,
        user_id: userId === '' ? undefined : userId,
        outcome: outcome || undefined,
        until: action === 'snooze' ? until : undefined,
      },
      { onSuccess: onDone },
    )
  }

  const others = (people.data ?? []).filter((u) => u.id !== s.author.id && !s.placements.some((p) => p.user.id === u.id))
  const valid =
    (!NEEDS_TEXT.has(action) || text.trim()) &&
    (action !== 'resolve' || (outcome && text.trim())) &&
    (!['delegate', 'share'].includes(action) || userId !== '')
  return (
    <form className="aform" onSubmit={submit}>
      {['delegate', 'share'].includes(action) && (
        <div className="field">
          <label htmlFor="a-user">{t(action === 'share' ? 'sheet.shareWith' : 'sheet.delegateTo')}</label>
          <select id="a-user" value={userId} onChange={(e) => setUserId(e.target.value ? Number(e.target.value) : '')}>
            <option value="">—</option>
            {others.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
          </select>
        </div>
      )}
      {action === 'resolve' && (
        <div className="toggles" role="radiogroup" aria-label={t('sheet.outcome')}>
          {OUTCOMES.map((o) => (
            <button type="button" key={o} className={`tgl ${outcome === o ? 'on' : ''}`} aria-pressed={outcome === o} onClick={() => setOutcome(o)}>
              {t(`outcome.${o}`)}
            </button>
          ))}
        </div>
      )}
      {action === 'snooze' && (
        <div className="toggles">
          <button type="button" className={`tgl ${until === addDays(1) ? 'on' : ''}`} onClick={() => setUntil(addDays(1))}>{t('sheet.tomorrow')}</button>
          <button type="button" className={`tgl ${until === addDays(7) ? 'on' : ''}`} onClick={() => setUntil(addDays(7))}>{t('sheet.inWeek')}</button>
          <input type="date" value={until} min={addDays(1)} onChange={(e) => setUntil(e.target.value)} aria-label={t('sheet.date')} />
        </div>
      )}
      {action !== 'snooze' && action !== 'share' && (
        <div className="field">
          <label htmlFor="a-text">{t(`sheet.prompt.${action}`)}</label>
          <textarea id="a-text" value={text} onChange={(e) => setText(e.target.value)} autoFocus />
        </div>
      )}
      {run.isError && <p className="error">{errorText(t, run.error)}</p>}
      <div className="actions">
        <button type="submit" className="btn primary" disabled={!valid || run.isPending}>{t(`action.${action}`)}</button>
        <button type="button" className="btn" onClick={onDone}>{t('common.cancel')}</button>
      </div>
    </form>
  )
}

function CommentBox({ s }: { s: StickerDetail }) {
  const { t } = useTranslation()
  const refresh = useInvalidateStickers()
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  const input = useRef<HTMLInputElement>(null)
  const send = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      let commentId: number | undefined
      if (text.trim()) {
        const d = await api<StickerDetail>(`stickers/${s.id}/actions`, { body: { action: 'comment', text } })
        commentId = d.thread[d.thread.length - 1]?.id
      }
      for (const f of files) await uploadFile(s.id, f, commentId)
      setText('')
      setFiles([])
      refresh(await api<StickerDetail>(`stickers/${s.id}`))
    } catch (x) {
      setErr(x)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="reply" onSubmit={send}>
      <div className="field">
        <label htmlFor="reply">{t('sheet.comment')}</label>
        <textarea id="reply" value={text} onChange={(e) => setText(e.target.value)} placeholder={t('sheet.write')} />
      </div>
      {files.length > 0 && <div className="files">{files.map((f) => <span key={f.name} className="file"><FileIcon />{f.name}</span>)}</div>}
      {err !== null && <p className="error">{errorText(t, err)}</p>}
      <div className="actions">
        <button type="submit" className="btn primary" disabled={busy || (!text.trim() && !files.length)}>{t('sheet.send')}</button>
        <button type="button" className="btn" onClick={() => input.current?.click()}><FileIcon />{t('sheet.attach')}</button>
        <input ref={input} type="file" multiple hidden onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
      </div>
    </form>
  )
}

function Editor({ s, onDone }: { s: StickerDetail; onDone: () => void }) {
  const { t } = useTranslation()
  const refresh = useInvalidateStickers()
  const [title, setTitle] = useState(s.title)
  const [body, setBody] = useState(s.body)
  const [err, setErr] = useState<unknown>(null)
  const save = async (e: FormEvent) => {
    e.preventDefault()
    try {
      refresh(await api<StickerDetail>(`stickers/${s.id}`, { method: 'PATCH', body: { title, body } }))
      onDone()
    } catch (x) {
      setErr(x)
    }
  }
  return (
    <form className="form" onSubmit={save}>
      <div className="field"><label htmlFor="e-title">{t('compose.title')}</label><input id="e-title" className="big" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} /></div>
      <div className="field"><label htmlFor="e-body">{t('compose.body')}</label><textarea id="e-body" value={body} onChange={(e) => setBody(e.target.value)} /></div>
      {err !== null && <p className="error">{errorText(t, err)}</p>}
      <div className="actions">
        <button className="btn primary" type="submit" disabled={!title.trim()}>{t('common.save')}</button>
        <button className="btn" type="button" onClick={onDone}>{t('common.cancel')}</button>
      </div>
    </form>
  )
}

export default function StickerSheet({ id, onClose }: { id: number; onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const q = useSticker(id)
  const move = useMove()
  const instantRun = useAction(id)
  const refresh = useInvalidateStickers()
  const [pending, setPending] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [showHistory, setShowHistory] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  useEffect(() => setPending(null), [id])

  const s = q.data
  if (q.isError) {
    return (
      <div className="scrim" onClick={onClose}>
        <div className="sheet narrow" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
          <div className="panel"><p>{t('sheet.notFound')}</p><button className="btn" onClick={onClose}>{t('common.close')}</button></div>
        </div>
      </div>
    )
  }
  if (!s) return <div className="scrim" />

  const lang = i18n.language
  const lk = looks(s.id, s.overdue)
  const mine = s.placements.find((p) => p.role !== 'viewer' && (s.my_role === 'recipient' || s.my_role === 'delegate' || s.kind === 'personal'))
  const canPlace = (s.my_role === 'recipient' || (s.my_role === 'delegate' && s.status === 'delegated')) &&
    ['new', 'triaged', 'in_progress', 'needs_info', 'delegated'].includes(s.status)
  const shownQ = s.my_quadrant ?? s.quadrant
  const delegates = s.placements.filter((p) => p.role === 'delegate')
  const buttons = ORDER.filter((a) => s.actions.includes(a))
  const sticker = s.files.filter((f) => f.comment_id === null)

  const setDeadline = async (v: string) => {
    refresh(await api<StickerDetail>(`stickers/${s.id}`, { method: 'PATCH', body: { deadline: v || null } }))
  }

  return (
    <div className="scrim" onClick={onClose}>
      <div className={`sheet ${toneOf(shownQ)}`} role="dialog" aria-modal="true" aria-label={s.title} onClick={(e) => e.stopPropagation()}>
        <button type="button" className="close close-m" onClick={onClose} aria-label={t('common.close')}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
        <div className="paperwrap">
          <div className="paper">
            <span className={`att ${lk.mount}`} aria-hidden />
            <div className="s-top"><span>{s.kind === 'personal' ? t('sticker.personal') : t(`quadrant.${shownQ}`)}</span></div>
            {editing ? <Editor s={s} onDone={() => setEditing(false)} /> : (
              <>
                <h2>{s.title}</h2>
                <div className="from">
                  <span className="ava lg" style={{ background: s.author.avatar_color }}>{initials(s.author.display_name)}</span>
                  <span>
                    <b>{s.author.display_name}</b>
                    <small>
                      {dateTime(s.created_at, lang)}
                      {s.kind === 'normal' && <> → {s.recipients.map((r) => r.display_name).join(', ')}</>}
                    </small>
                  </span>
                </div>
                {s.body && <p className="body">{s.body}</p>}
                <Files files={sticker} />
                {s.can_edit && <button type="button" className="btn small-btn" onClick={() => setEditing(true)}>{t('sheet.edit')}</button>}
              </>
            )}
          </div>
          <div className="thread">
            {s.thread.map((c) => (
              <div key={c.id} className={`msg k-${c.kind}`}>
                <span className="ava" style={{ background: c.author.avatar_color }}>{initials(c.author.display_name)}</span>
                <div className="bubble">
                  <small>{c.author.display_name} · {dateTime(c.created_at, lang)}{c.kind !== 'comment' && <> · <b>{t(`commentKind.${c.kind}`)}</b></>}</small>
                  <p>{c.body}</p>
                  <Files files={s.files.filter((f) => f.comment_id === c.id)} />
                </div>
              </div>
            ))}
            {s.reject_reason && <p className="note-late">{t('sheet.rejected')}: {s.reject_reason}</p>}
          </div>
          {s.actions.includes('comment') && <CommentBox s={s} />}
        </div>

        <div className="panel">
          <div className="panel-top">
            <span className="chip">№{s.id}</span>
            {s.deadline && <span className={`chip ${s.overdue ? 'late' : ''}`}>{t('sheet.due')} {shortDate(s.deadline, lang)}</span>}
            {s.escalated && <span className="chip">{t('sheet.escalated')}</span>}
            <button type="button" className="close" onClick={onClose} aria-label={t('common.close')}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M6 6l12 12M18 6L6 18" /></svg>
            </button>
          </div>

          {s.kind === 'normal' && (
            <div><p className="label">{t('sheet.progress')}</p><Steps status={s.status} /></div>
          )}

          <div>
            <p className="label">{t('sheet.quadrant')}</p>
            {canPlace ? (
              <div className="qgrid">
                {QUADRANTS.map((qq) => (
                  <button key={qq} type="button" className={`qbtn ${toneOf(qq)} ${mine?.quadrant === qq ? 'on' : ''}`}
                    onClick={() => move.mutate({ id: s.id, quadrant: qq })} aria-pressed={mine?.quadrant === qq}>
                    <i />{t(`quadrant.${qq}`)}
                  </button>
                ))}
              </div>
            ) : (
              <p className="qline"><i className={toneOf(s.quadrant)} />{t(`quadrant.${s.quadrant}`)}</p>
            )}
            {s.kind === 'normal' && <p className="est">{t('sheet.authorEstimate')}: {t(`quadrant.${s.author_quadrant}`)}</p>}
            {s.my_role === 'author' && s.kind === 'normal' && (
              <p className="est">{s.decided_quadrant ? `${t('sheet.decision')}: ${t(`quadrant.${s.decided_quadrant}`)}` : t('sheet.notTriaged')}</p>
            )}
            {s.my_role === 'delegate' && s.decided_quadrant && <p className="est">{t('sheet.decision')}: {t(`quadrant.${s.decided_quadrant}`)}</p>}
            {delegates.map((p) => (
              <p className="est" key={p.user.id}>{t('sheet.delegateBoard', { name: p.user.display_name })}: {p.quadrant ? t(`quadrant.${p.quadrant}`) : '—'}</p>
            ))}
          </div>

          <div>
            <p className="label">{t('sheet.deadline')}</p>
            {s.can_edit_deadline ? (
              <div className="row">
                <input type="date" className="date" value={s.deadline ?? ''} onChange={(e) => setDeadline(e.target.value)} aria-label={t('sheet.deadline')} />
                {s.deadline && <button type="button" className="btn" onClick={() => setDeadline('')}>{t('sheet.noDeadline')}</button>}
              </div>
            ) : <p className="est">{s.deadline ? shortDate(s.deadline, lang) : t('sheet.noDeadlineSet')}</p>}
          </div>

          {s.outcome && <p className="outcome"><b>{t('sheet.outcome')}:</b> {t(`outcome.${s.outcome}`)}</p>}
          {s.snoozed_until && <p className="est">{t('sheet.snoozedUntil')} {shortDate(s.snoozed_until, lang)}</p>}

          {(buttons.length > 0 || s.actions.includes('share')) && (
            <div>
              <p className="label">{t('sheet.actions')}</p>
              {pending ? (
                <ActionForm key={pending} s={s} action={pending} onDone={() => setPending(null)} />
              ) : (
                <div className="actions">
                  {buttons.map((a, i) => (
                    <button key={a} type="button" className={`btn ${i === 0 ? 'primary' : ''}`} disabled={instantRun.isPending}
                      onClick={() => (isInstant(s, a) ? instantRun.mutate({ action: a }) : setPending(a))}>
                      {t(s.kind === 'personal' && a === 'resolve' ? 'action.done' : `action.${a}`)}
                    </button>
                  ))}
                  {s.actions.includes('share') && <button type="button" className="btn" onClick={() => setPending('share')}>{t('action.share')}</button>}
                </div>
              )}
              {instantRun.isError && <p className="error">{errorText(t, instantRun.error)}</p>}
            </div>
          )}

          <div>
            <button type="button" className="linkish" onClick={() => setShowHistory((v) => !v)} aria-expanded={showHistory}>
              {t('sheet.history')} ({s.history.length})
            </button>
            {showHistory && (
              <ul className="history">
                {s.history.map((h) => (
                  <li key={h.id}><small>{dateTime(h.at, lang)} · {h.actor?.display_name ?? t('sheet.system')}</small>{historyLine(h, t)}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
