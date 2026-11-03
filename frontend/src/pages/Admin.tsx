import { useEffect, useState, type FormEvent } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Department, type LoginEvent, type Role, type User } from '../api'
import { errorText, useMe } from '../session'
import { Avatar } from '../Shell'
import AdminTelegram from './AdminTelegram'
import AdminChannels from './AdminChannels'
import { stamp } from '../dates'

export default function AdminPage({ me }: { me: User }) {
  const { t } = useTranslation()
  return (
    <>
      <h1>{t('nav.admin')}</h1>
      <div className="tabs">
        <NavLink to="/admin" end>{t('admin.users')}</NavLink>
        <NavLink to="/admin/departments">{t('admin.departments')}</NavLink>
        <NavLink to="/admin/logins">{t('admin.logins')}</NavLink>
        <NavLink to="/admin/telegram">Telegram</NavLink>
        <NavLink to="/admin/updates">{t('ch.tab')}</NavLink>
      </div>
      <Routes>
        <Route index element={<Users me={me} />} />
        <Route path="departments" element={<Departments />} />
        <Route path="logins" element={<Logins />} />
        <Route path="telegram" element={<AdminTelegram />} />
        <Route path="updates" element={<AdminChannels />} />
      </Routes>
    </>
  )
}

const useUsers = () => useQuery({ queryKey: ['admin', 'users'], queryFn: () => api<User[]>('admin/users') })
const useDepartments = () => useQuery({ queryKey: ['admin', 'departments'], queryFn: () => api<Department[]>('admin/departments') })

function Modal({ title, onClose, onSubmit, error, busy, children, left }: {
  title: string; onClose: () => void; onSubmit: (e: FormEvent) => void; error: string; busy: boolean; children: React.ReactNode
  left?: React.ReactNode
}) {
  const { t } = useTranslation()
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="card modal stack" onSubmit={onSubmit}>
        <h2>{title}</h2>
        {children}
        {error && <div className="error">{error}</div>}
        <div className="row">
          {left}
          <span className="spacer" />
          <button type="button" className="ghost" onClick={onClose}>{t('admin.cancel')}</button>
          <button className="primary" disabled={busy}>{t('admin.save')}</button>
        </div>
      </form>
    </div>
  )
}

function useSave(path: string, onDone: () => void) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const m = useMutation({
    mutationFn: ({ method, url, body }: { method: string; url: string; body: unknown }) => api(url, { method, body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin'] })
      qc.invalidateQueries({ queryKey: ['me'] })
      onDone()
    },
  })
  return { ...m, errorMsg: m.error ? errorText(t, m.error) : '', path }
}

type UserForm = {
  login: string; first_name: string; last_name: string; email: string; password: string; role: Role; is_admin: boolean
  is_active: boolean; department_id: number | null; reset_2fa: boolean; telegram_unlink: boolean
}

function UserDialog({ user, onClose }: { user: User | null; onClose: () => void }) {
  const { t } = useTranslation()
  const depts = useDepartments().data ?? []
  const [f, setF] = useState<UserForm>({
    login: user?.login ?? '', first_name: user?.first_name ?? '', last_name: user?.last_name ?? '', email: user?.email ?? '', password: '',
    role: user?.role ?? 'employee', is_admin: user?.is_admin ?? false, is_active: user?.is_active ?? true,
    department_id: user?.department_id ?? depts[0]?.id ?? null, reset_2fa: false, telegram_unlink: false,
  })
  const save = useSave('admin/users', onClose)
  // the "new password" field only appears on request: otherwise Chrome fills it (and the e-mail field) with the
  // admin's own saved login, which blocks saving or silently resets the employee's password
  const [pwOpen, setPwOpen] = useState(!user)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const del = useSave('admin/users', onClose)
  const isMe = useMe().data?.user.id === user?.id
  // login is generated from the name until the admin edits it by hand
  const [loginTouched, setLoginTouched] = useState(!!user)
  useEffect(() => {
    if (loginTouched || !f.first_name.trim() || !f.last_name.trim()) return
    const id = setTimeout(async () => {
      const q = new URLSearchParams({ first_name: f.first_name.trim(), last_name: f.last_name.trim() })
      try {
        const { login } = await api<{ login: string }>(`admin/login-suggestion?${q}`)
        setF((cur) => ({ ...cur, login }))
      } catch { /* keep the field as is */ }
    }, 250)
    return () => clearTimeout(id)
  }, [f.first_name, f.last_name, loginTouched])
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const common = { first_name: f.first_name.trim(), last_name: f.last_name.trim(), email: f.email || null, role: f.role, is_admin: f.is_admin, department_id: f.department_id }
    if (user) {
      save.mutate({
        method: 'PATCH', url: `admin/users/${user.id}`,
        body: { ...common, is_active: f.is_active, reset_2fa: f.reset_2fa, telegram_unlink: f.telegram_unlink, ...(f.password ? { password: f.password } : {}) },
      })
    } else {
      save.mutate({ method: 'POST', url: 'admin/users', body: { ...common, login: f.login, password: f.password } })
    }
  }
  return (
    <Modal title={user ? user.display_name : t('admin.addUser')} onClose={onClose} onSubmit={submit} error={save.errorMsg || del.errorMsg}
      busy={save.isPending || del.isPending}
      left={user && !isMe && (confirmDelete ? (
        <span className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <span className="small">{t('admin.deleteConfirm')}</span>
          <button type="button" className="danger" disabled={del.isPending} onClick={() => del.mutate({ method: 'DELETE', url: `admin/users/${user.id}`, body: undefined })}>{t('admin.deleteYes')}</button>
          <button type="button" className="ghost" onClick={() => setConfirmDelete(false)}>{t('admin.cancel')}</button>
        </span>
      ) : (
        <button type="button" className="ghost danger" onClick={() => setConfirmDelete(true)}>{t('admin.delete')}</button>
      ))}>
      <div className="grid2">
        <label className="field">{t('admin.firstName')}<input required autoFocus={!user} value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} /></label>
        <label className="field">{t('admin.lastName')}<input required value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} /></label>
        <label className="field">{t('admin.login')}
          <input required disabled={!!user} pattern="[A-Za-z0-9._\-]+" value={f.login} placeholder="o.zhuravlev"
            onChange={(e) => { setLoginTouched(true); setF({ ...f, login: e.target.value }) }} />
          {!user && <span className="small">{t('admin.loginHint')}</span>}
        </label>
        <label className="field">{t('admin.email')}<input type="email" autoComplete="off" name="employee-email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
        <label className="field">{t('admin.department')}
          <select value={f.department_id ?? ''} onChange={(e) => setF({ ...f, department_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">{t('admin.noDepartment')}</option>
            {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>
        <label className="field">{t('admin.role')}
          <select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>
            <option value="employee">{t('role.employee')}</option>
            <option value="manager">{t('role.manager')}</option>
          </select>
        </label>
      </div>
      {pwOpen ? (
        <>
          <label className="field">{user ? t('admin.newPassword') : t('admin.password')}
            <input type="password" autoComplete="new-password" name="employee-new-password" required={!user} value={f.password}
              autoFocus={!!user} onChange={(e) => setF({ ...f, password: e.target.value })} />
          </label>
          <span className="muted small">{t('password.hint')}</span>
        </>
      ) : (
        <button type="button" className="ghost" style={{ alignSelf: 'flex-start' }} onClick={() => setPwOpen(true)}>{t('admin.setPassword')}</button>
      )}
      <label className="check"><input type="checkbox" checked={f.is_admin} onChange={(e) => setF({ ...f, is_admin: e.target.checked })} />{t('admin.admin')}</label>
      {user && <label className="check"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} />{t('admin.active')}</label>}
      {user?.totp_enabled && <label className="check"><input type="checkbox" checked={f.reset_2fa} onChange={(e) => setF({ ...f, reset_2fa: e.target.checked })} />{t('admin.reset2fa')}</label>}
      {user?.telegram_linked && <label className="check"><input type="checkbox" checked={f.telegram_unlink} onChange={(e) => setF({ ...f, telegram_unlink: e.target.checked })} />{t('tg.adminUnlink', { name: user.telegram_username ?? '' })}</label>}
    </Modal>
  )
}

function Users({ me }: { me: User }) {
  const { t } = useTranslation()
  const users = useUsers().data ?? []
  const depts = useDepartments().data ?? []
  const [edit, setEdit] = useState<User | null | 'new'>(null)
  const deptName = (id: number | null) => depts.find((d) => d.id === id)?.name ?? '—'
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="spacer" />
        <button className="primary" onClick={() => setEdit('new')}>{t('admin.addUser')}</button>
      </div>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>{t('admin.name')}</th><th>{t('admin.login')}</th><th>{t('admin.department')}</th><th>{t('admin.role')}</th><th>{t('admin.twofa')}</th><th /></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.55 }}>
                <td><div className="row"><Avatar name={u.display_name} color={u.avatar_color} size={28} />{u.display_name}{u.id === me.id && <span className="muted small">({t('admin.you')})</span>}</div></td>
                <td>{u.login}</td>
                <td>{deptName(u.department_id)}</td>
                <td>{t(`role.${u.role}`)}{u.is_admin && <> · <span className="pill">{t('admin.admin')}</span></>}{!u.is_active && <> · <span className="pill bad">{t('admin.blocked')}</span></>}</td>
                <td>{u.totp_enabled ? <span className="pill good">✓</span> : <span className="muted">—</span>}</td>
                <td style={{ textAlign: 'right' }}><button className="ghost" onClick={() => setEdit(u)}>{t('admin.edit')}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {edit && <UserDialog user={edit === 'new' ? null : edit} onClose={() => setEdit(null)} />}
    </div>
  )
}

function DepartmentDialog({ dept, onClose }: { dept: Department | null; onClose: () => void }) {
  const { t } = useTranslation()
  const managers = (useUsers().data ?? []).filter((u) => u.role === 'manager' && u.is_active)
  const [name, setName] = useState(dept?.name ?? '')
  const [managerId, setManagerId] = useState<number | null>(dept?.manager_id ?? null)
  const save = useSave('admin/departments', onClose)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate({
      method: dept ? 'PATCH' : 'POST', url: dept ? `admin/departments/${dept.id}` : 'admin/departments',
      body: { name, manager_id: managerId },
    })
  }
  return (
    <Modal title={dept ? dept.name : t('admin.addDepartment')} onClose={onClose} onSubmit={submit} error={save.errorMsg} busy={save.isPending}>
      <label className="field">{t('admin.name')}<input required value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label className="field">{t('admin.manager')}
        <select value={managerId ?? ''} onChange={(e) => setManagerId(e.target.value ? Number(e.target.value) : null)}>
          <option value="">{t('admin.noManager')}</option>
          {managers.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
        </select>
      </label>
    </Modal>
  )
}

function Departments() {
  const { t } = useTranslation()
  const depts = useDepartments().data ?? []
  const users = useUsers().data ?? []
  const [edit, setEdit] = useState<Department | null | 'new'>(null)
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="spacer" />
        <button className="primary" onClick={() => setEdit('new')}>{t('admin.addDepartment')}</button>
      </div>
      <table className="table">
        <thead><tr><th>{t('admin.name')}</th><th>{t('admin.manager')}</th><th>{t('admin.users')}</th><th /></tr></thead>
        <tbody>
          {depts.map((d) => (
            <tr key={d.id}>
              <td>{d.name}</td>
              <td>{users.find((u) => u.id === d.manager_id)?.display_name ?? <span className="muted">{t('admin.noManager')}</span>}</td>
              <td>{users.filter((u) => u.department_id === d.id).length}</td>
              <td style={{ textAlign: 'right' }}><button className="ghost" onClick={() => setEdit(d)}>{t('admin.edit')}</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {edit && <DepartmentDialog dept={edit === 'new' ? null : edit} onClose={() => setEdit(null)} />}
    </div>
  )
}

function Logins() {
  const { t, i18n } = useTranslation()
  const events = useQuery({ queryKey: ['admin', 'logins'], queryFn: () => api<LoginEvent[]>('admin/logins') }).data ?? []
  return (
    <div className="card table-wrap">
      <table className="table">
        <thead><tr><th>{t('admin.when')}</th><th>{t('admin.who')}</th><th>{t('admin.result')}</th><th>{t('admin.ip')}</th><th>{t('admin.device')}</th></tr></thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.id}>
              <td style={{ whiteSpace: 'nowrap' }}>{stamp(e.at, i18n.language)}</td>
              <td>{e.login}</td>
              <td><span className={`pill ${e.success ? 'good' : 'bad'}`}>{t(`reason.${e.reason ?? 'ok'}`)}</span></td>
              <td>{e.ip ?? '—'}</td>
              <td className="muted small" style={{ maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={e.user_agent ?? ''}>{e.user_agent}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
