import { useQuery } from '@tanstack/react-query'
import { useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type Department, type User } from '../api'
import { errorText } from '../session'
import { uploadFile, useDirectory, useInvalidateStickers, type StickerDetail } from '../stickers'
import { FileIcon } from './StickerSheet'

export default function Compose({ user, onClose, onCreated }: { user: User; onClose: () => void; onCreated: (id: number) => void }) {
  const { t } = useTranslation()
  const people = useDirectory()
  const depts = useQuery({ queryKey: ['departments'], queryFn: () => api<Department[]>('directory/departments'), staleTime: 60_000 })
  const refresh = useInvalidateStickers()
  const myDept = depts.data?.find((d) => d.id === user.department_id)
  const defaultTo = myDept?.manager_id && myDept.manager_id !== user.id ? myDept.manager_id : null

  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [urgent, setUrgent] = useState(false)
  const [important, setImportant] = useState(false)
  const [deadline, setDeadline] = useState('')
  const [to, setTo] = useState<number | 'me' | null>(null) // null = department manager
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  const input = useRef<HTMLInputElement>(null)

  const target: number | 'me' = to ?? defaultTo ?? 'me'
  const others = (people.data ?? []).filter((u) => u.id !== user.id)
  const managers = others.filter((u) => u.role === 'manager')
  const colleagues = others.filter((u) => u.role !== 'manager')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      const s = await api<StickerDetail>('stickers', {
        body: {
          title, body, urgent, important, deadline: deadline || null,
          personal: target === 'me',
          recipient_ids: typeof target === 'number' ? [target] : [],
        },
      })
      for (const f of files) await uploadFile(s.id, f)
      refresh()
      onCreated(s.id)
    } catch (x) {
      setErr(x)
      setBusy(false)
    }
  }

  return (
    <div className="scrim" onClick={onClose}>
      <div className="sheet narrow" role="dialog" aria-modal="true" aria-label={t('compose.heading')} onClick={(e) => e.stopPropagation()}>
        <form className="panel form" onSubmit={submit}>
          <div className="panel-top">
            <h2 style={{ margin: 0 }}>{t('compose.heading')}</h2>
            <button type="button" className="close" onClick={onClose} aria-label={t('common.close')}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M6 6l12 12M18 6L6 18" /></svg>
            </button>
          </div>
          <div className="field">
            <label htmlFor="c-to">{t('compose.to')}</label>
            <select id="c-to" value={String(target)}
              onChange={(e) => setTo(e.target.value === 'me' ? 'me' : Number(e.target.value))}>
              {managers.length > 0 && (
                <optgroup label={t('compose.managers')}>
                  {managers.map((u) => <option key={u.id} value={u.id}>{u.display_name}{u.id === defaultTo ? ` · ${t('compose.myManager')}` : ''}</option>)}
                </optgroup>
              )}
              {colleagues.length > 0 && (
                <optgroup label={t('compose.colleagues')}>
                  {colleagues.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
                </optgroup>
              )}
              <option value="me">{t('compose.toMe')}</option>
            </select>
            {target === 'me' && <p className="hint">{t('compose.toMeHint')}</p>}
          </div>
          <div className="field">
            <label htmlFor="c-title">{t('compose.title')}</label>
            <input id="c-title" className="big" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder={t('compose.titlePh')} autoFocus />
          </div>
          <div className="field">
            <label htmlFor="c-body">{t('compose.body')}</label>
            <textarea id="c-body" value={body} onChange={(e) => setBody(e.target.value)} placeholder={t('compose.bodyPh')} />
          </div>
          <div>
            <p className="label">{t('compose.estimate')}</p>
            <div className="toggles">
              <button type="button" className={`tgl ${urgent ? 'on' : ''}`} aria-pressed={urgent} onClick={() => setUrgent(!urgent)}>{t('compose.urgent')}</button>
              <button type="button" className={`tgl ${important ? 'on' : ''}`} aria-pressed={important} onClick={() => setImportant(!important)}>{t('compose.important')}</button>
            </div>
            {target !== 'me' && <p className="hint">{t('compose.estimateHint')}</p>}
          </div>
          <div className="row">
            <div className="field">
              <label htmlFor="c-deadline">{t('compose.deadline')}</label>
              <input id="c-deadline" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
            </div>
            <div className="field">
              <label>{t('compose.files')}</label>
              <button type="button" className="btn" onClick={() => input.current?.click()}><FileIcon />{files.length ? t('compose.nFiles', { count: files.length }) : t('sheet.attach')}</button>
              <input ref={input} type="file" multiple hidden onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
            </div>
          </div>
          {err !== null && <p className="error">{errorText(t, err)}</p>}
          <div className="actions">
            <button type="submit" className="btn primary" disabled={busy || !title.trim() || !target}>{t('compose.send')}</button>
            <button type="button" className="btn" onClick={onClose}>{t('common.cancel')}</button>
          </div>
        </form>
      </div>
    </div>
  )
}
