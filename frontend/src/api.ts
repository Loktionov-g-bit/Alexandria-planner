import type { Lang } from './i18n'
export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `HTTP ${status}`)
    this.status = status
    this.detail = detail
  }
  /** i18n keys from the backend ("auth.invalid", ["password.too_short", ...]) */
  get keys(): string[] {
    if (typeof this.detail === 'string') return [this.detail]
    if (Array.isArray(this.detail) && this.detail.every((d) => typeof d === 'string')) return this.detail as string[]
    return ['error.validation']
  }
}

export async function api<T = unknown>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  // relative URL: resolved against <base href>, so sub-path deployments work
  const res = await fetch(`api/${path}`, {
    method: opts.method ?? (opts.body === undefined ? 'GET' : 'POST'),
    headers: opts.body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    credentials: 'same-origin',
  })
  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? null)
  return data as T
}

export type Role = 'employee' | 'manager'

export interface User {
  id: number
  login: string
  display_name: string
  first_name: string
  last_name: string
  email: string | null
  role: Role
  is_admin: boolean
  is_active: boolean
  department_id: number | null
  avatar_color: string
  locale: Lang
  timezone: string
  theme: 'system' | 'light' | 'dark'
  totp_enabled: boolean
  needs_2fa: boolean
  notify_push: boolean
  notify_telegram: boolean
  digest_morning: boolean
  digest_evening: boolean
  digest_time: string
  digest_days: string
  digest_skip_empty: boolean
  telegram_username: string | null
  telegram_linked: boolean
}

export interface Me {
  user: User
  verified: boolean
  pending: null | 'totp' | 'totp_setup'
  channel: string
}

export interface Department {
  id: number
  name: string
  manager_id: number | null
}

export interface LoginEvent {
  id: number
  user_id: number | null
  login: string
  at: string
  ip: string | null
  user_agent: string | null
  success: boolean
  reason: string | null
}
