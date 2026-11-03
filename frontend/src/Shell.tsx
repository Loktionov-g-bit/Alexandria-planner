import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, type Department, type Me } from './api'
import { useSetMe, useSolo } from './session'
import { useBoard, type StickerSummary } from './stickers'
import Bell from './components/Bell'

export function Avatar({ name, color, size = 32 }: { name: string; color: string; size?: number }) {
  const initials = name.split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase()
  return <span className="avatar" style={{ background: color, width: size, height: size }} aria-hidden>{initials}</span>
}

const TelegramIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M21.9 4.3 18.7 19.4c-.2 1-.9 1.3-1.7.8l-4.8-3.5-2.3 2.2c-.3.3-.5.5-1 .5l.3-4.9 8.9-8c.4-.3-.1-.5-.6-.2L6.4 13.2 1.7 11.7c-1-.3-1-1 .2-1.5L20.6 3c.9-.3 1.6.2 1.3 1.3z"/></svg>
)
const GithubIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M12 .5a11.5 11.5 0 0 0-3.6 22.4c.6.1.8-.3.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.2 1.2a11 11 0 0 1 5.8 0c2.2-1.5 3.2-1.2 3.2-1.2.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.2c0 .3.2.7.8.6A11.5 11.5 0 0 0 12 .5z"/></svg>
)

export function AuthorLinks({ className = 'author' }: { className?: string }) {
  const { t } = useTranslation()
  return (
    <div className={className}>
      <span>{t('footer.author')}</span>
      <a href="https://t.me/marshall033" target="_blank" rel="noreferrer" aria-label="Telegram"><TelegramIcon /></a>
      <a href="https://github.com/Loktionov-g-bit" target="_blank" rel="noreferrer" aria-label="GitHub"><GithubIcon /></a>
    </div>
  )
}

const I = ({ children }: { children: ReactNode }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>{children}</svg>
)
const ICONS: Record<string, ReactNode> = {
  board: <I><rect x="3.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="3.5" y="13.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="13.5" width="7" height="7" rx="1.5" /></I>,
  sent: <I><path d="M4 12l16-8-6 16-2.5-6.5z" /></I>,
  archive: <I><rect x="3.5" y="4" width="17" height="5" rx="1.5" /><path d="M5.5 9v9.5a1.5 1.5 0 0 0 1.5 1.5h10a1.5 1.5 0 0 0 1.5-1.5V9M10 13h4" /></I>,
  stats: <I><path d="M5 20V11M12 20V5M19 20v-6" /></I>,
  admin: <I><circle cx="12" cy="12" r="3" /><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8" /></I>,
  profile: <I><circle cx="12" cy="8.5" r="3.5" /><path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6" /></I>,
}

export default function Shell({ me, children }: { me: Me; children: ReactNode }) {
  const { t } = useTranslation()
  const setMe = useSetMe()
  const u = me.user
  const board = useBoard()
  const solo = useSolo()
  const sent = useQuery({ queryKey: ['sent'], queryFn: () => api<StickerSummary[]>('stickers/sent') })
  const depts = useQuery({ queryKey: ['departments'], queryFn: () => api<Department[]>('directory/departments'), staleTime: 60_000 })
  const dept = depts.data?.find((d) => d.id === u.department_id)
  const asks = (sent.data ?? []).filter((s) => s.status === 'needs_info').length
  const logout = async () => {
    await api('auth/logout', { method: 'POST' })
    setMe(null)
  }
  const link = (to: string, key: string, n?: ReactNode) => (
    <NavLink to={to} end={to === '/'}>{ICONS[key]}<span className="lbl">{t(`nav.${key}`)}</span>{n}</NavLink>
  )
  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <img src="alexandria-planner-logo.svg" alt="" />
          <div>
            <b>{t('app.brand')}</b>
            <span>{t('app.name')}</span>
          </div>
          {me.channel === 'beta' && <span className="beta-badge">{t('app.beta')}</span>}
          <span className="spacer" />
          <Bell />
        </div>
        <nav>
          {link('/', 'board', board.data?.length ? <span className="n">{board.data.length}</span> : null)}
          {!solo && link('/sent', 'sent', asks ? <span className="n late" title={t('board.kpi.waitingMe')}>{asks}</span> : null)}
          {link('/archive', 'archive')}
          {!solo && link('/stats', 'stats')}
          {u.is_admin && link('/admin', 'admin')}
          {link('/profile', 'profile')}
        </nav>
        <div className="me">
          <Avatar name={u.display_name} color={u.avatar_color} size={36} />
          <div className="who">
            <b>{u.first_name || u.display_name.split(' ')[0]}</b>
            <span>{solo ? t('mode.solo') : dept?.name ?? t(`role.${u.role}`)}</span>
          </div>
          <button className="iconbtn" onClick={logout} aria-label={t('nav.logout')} title={t('nav.logout')}>
            <I><path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4M10 16l-4-4 4-4M6 12h10" /></I>
          </button>
        </div>
        <AuthorLinks />
      </aside>
      <main className="main">{children}</main>
    </div>
  )
}
