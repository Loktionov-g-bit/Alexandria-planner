import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useFeed, type NotificationItem } from '../notifications'
import { initials } from '../stickers'
import { ago } from '../dates'


export default function Bell() {
  const { t, i18n } = useTranslation()
  const feed = useFeed()
  const qc = useQueryClient()
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const unread = feed.data?.unread ?? 0

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])

  const markRead = async (ids?: number[]) => {
    await api('notifications/read', { body: { ids: ids ?? null } })
    qc.invalidateQueries({ queryKey: ['notifications'] })
  }
  const go = (n: NotificationItem) => {
    if (!n.read) markRead([n.id])
    setOpen(false)
    if (n.sticker_id) nav(`/?s=${n.sticker_id}`)
  }

  return (
    <div className="bellbox" ref={box}>
      <button type="button" className="iconbtn bell" aria-label={t('feed.title')} aria-expanded={open} onClick={() => setOpen(!open)}>
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M6 9.5a6 6 0 0 1 12 0c0 5 2 6.5 2 6.5H4s2-1.5 2-6.5" /><path d="M10 19.5a2.2 2.2 0 0 0 4 0" />
        </svg>
        {unread > 0 && <span className="badge">{unread > 99 ? '99+' : unread}</span>}
      </button>
      {open && (
        <div className="feed" role="dialog" aria-label={t('feed.title')}>
          <div className="feed-head">
            <h2>{t('feed.title')}</h2>
            {unread > 0 && <button type="button" className="linkish" onClick={() => markRead()}>{t('feed.readAll')}</button>}
          </div>
          {!feed.data?.items.length ? <p className="feed-empty">{t('feed.empty')}</p> : (
            <ul>
              {feed.data.items.map((n) => (
                <li key={n.id}>
                  <button type="button" className={`note ${n.read ? '' : 'unread'}`} onClick={() => go(n)}>
                    {n.actor
                      ? <span className="ava" style={{ background: n.actor.avatar_color }} aria-hidden>{initials(n.actor.display_name)}</span>
                      : <span className="ava sys" aria-hidden>A</span>}
                    <span className="nt">
                      <b>{n.title}</b>
                      {n.body && <span>{n.body}</span>}
                      <small>{ago(n.created_at, i18n.language)}</small>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
