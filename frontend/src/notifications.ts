import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api } from './api'
import type { UserBrief } from './stickers'

export interface NotificationItem {
  id: number
  event: string
  sticker_id: number | null
  title: string
  body: string
  actor: UserBrief | null
  created_at: string
  read: boolean
}

export const useFeed = () =>
  useQuery({ queryKey: ['notifications'], queryFn: () => api<{ unread: number; items: NotificationItem[] }>('notifications'), refetchInterval: 120_000 })

/** Server-Sent Events: the server pings when something on my stickers changed; refetch what is on screen. */
export function useLive(enabled: boolean) {
  const qc = useQueryClient()
  useEffect(() => {
    if (!enabled || typeof EventSource === 'undefined') return
    const es = new EventSource('api/live')
    let t: ReturnType<typeof setTimeout> | undefined
    es.onmessage = () => {
      clearTimeout(t)
      t = setTimeout(() => {
        for (const k of ['board', 'sent', 'shared', 'archive', 'notifications', 'sticker']) qc.invalidateQueries({ queryKey: [k] })
      }, 150)
    }
    return () => { clearTimeout(t); es.close() }
  }, [enabled, qc])
}

// ---------------------------------------------------------------- Web Push on this device

export type PushState = 'unsupported' | 'insecure' | 'ios-install' | 'denied' | 'off' | 'on'

const isIos = () => /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
const standalone = () => window.matchMedia('(display-mode: standalone)').matches || (navigator as unknown as { standalone?: boolean }).standalone === true

export async function pushState(): Promise<PushState> {
  if (!window.isSecureContext) return 'insecure'
  if (isIos() && !standalone()) return 'ios-install'
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) return 'unsupported'
  if (Notification.permission === 'denied') return 'denied'
  const reg = await navigator.serviceWorker.getRegistration()
  const sub = await reg?.pushManager.getSubscription()
  return sub && Notification.permission === 'granted' ? 'on' : 'off'
}

function keyBytes(b64: string) {
  const s = atob(b64.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (b64.length % 4)) % 4))
  return Uint8Array.from(s, (c) => c.charCodeAt(0))
}

export async function enablePush() {
  const perm = await Notification.requestPermission()
  if (perm !== 'granted') throw new Error('denied')
  const reg = await navigator.serviceWorker.ready
  const { key } = await api<{ key: string }>('push/key')
  const sub = (await reg.pushManager.getSubscription()) ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) }))
  await api('push/subscribe', { body: sub.toJSON() })
}

export async function disablePush() {
  const reg = await navigator.serviceWorker.getRegistration()
  const sub = await reg?.pushManager.getSubscription()
  if (sub) {
    await api('push/unsubscribe', { body: sub.toJSON() }).catch(() => undefined)
    await sub.unsubscribe()
  }
}
