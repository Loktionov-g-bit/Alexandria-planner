import { useQuery } from '@tanstack/react-query'
import { Navigate, Route, Routes } from 'react-router-dom'
import { api } from './api'
import { useMe, usePreferences } from './session'
import { useLive } from './notifications'
import { LoginPage, SetupPage, TotpPage } from './pages/Auth'
import Shell from './Shell'
import BoardPage from './pages/Board'
import AdminPage from './pages/Admin'
import ProfilePage from './pages/Profile'
import { ArchivePage, SentPage } from './pages/Lists'
import StatsPage from './pages/Stats'

export default function App() {
  const setup = useQuery({ queryKey: ['setup'], queryFn: () => api<{ needed: boolean }>('setup') })
  const me = useMe()
  usePreferences(me.data)
  useLive(!!me.data && !me.data.pending)

  if (setup.isLoading || me.isLoading) return null
  if (setup.data?.needed) return <SetupPage />
  if (!me.data) return <LoginPage />
  if (me.data.pending) return <TotpPage me={me.data} />

  const user = me.data.user
  return (
    <Shell me={me.data}>
      <Routes>
        <Route path="/" element={<BoardPage user={user} />} />
        {me.data.mode === 'team' && <Route path="/sent" element={<SentPage user={user} />} />}
        <Route path="/archive" element={<ArchivePage />} />
        {me.data.mode === 'team' && <Route path="/stats" element={<StatsPage />} />}
        <Route path="/profile" element={<ProfilePage me={me.data} />} />
        {user.is_admin && <Route path="/admin/*" element={<AdminPage me={user} />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  )
}
