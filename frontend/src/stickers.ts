import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, type Role } from './api'

export type Quadrant = 'do' | 'plan' | 'delegate' | 'drop'
export const QUADRANTS: Quadrant[] = ['do', 'plan', 'delegate', 'drop']
export type Status =
  | 'new' | 'triaged' | 'in_progress' | 'needs_info' | 'delegated'
  | 'resolved' | 'closed' | 'snoozed' | 'rejected' | 'withdrawn'
export type Outcome = 'approved' | 'declined' | 'done' | 'fyi'
export type MyRole = 'author' | 'recipient' | 'delegate' | 'viewer'

export interface UserBrief {
  id: number
  display_name: string
  avatar_color: string
  role: Role
  department_id: number | null
}

export interface StickerSummary {
  id: number
  kind: 'normal' | 'personal'
  title: string
  body: string
  author: UserBrief
  status: Status
  author_quadrant: Quadrant
  decided_quadrant: Quadrant | null
  quadrant: Quadrant
  escalated: boolean
  deadline: string | null
  overdue: boolean
  snoozed_until: string | null
  outcome: Outcome | null
  reject_reason: string | null
  created_at: string
  updated_at: string
  recipients: UserBrief[]
  my_role: MyRole
  my_quadrant: Quadrant | null
  comments: number
  attachments: number
}

export interface Attachment { id: number; comment_id: number | null; filename: string; content_type: string; size: number; created_at: string }
export interface Comment { id: number; author: UserBrief; kind: 'comment' | 'question' | 'answer' | 'report' | 'resolution'; body: string; created_at: string }
export interface AuditEvent { id: number; actor: UserBrief | null; at: string; action: string; data: Record<string, unknown> }

export interface StickerDetail extends StickerSummary {
  placements: { user: UserBrief; role: 'recipient' | 'delegate' | 'viewer'; quadrant: Quadrant | null }[]
  thread: Comment[]
  files: Attachment[]
  history: AuditEvent[]
  actions: string[]
  can_edit: boolean
  can_edit_deadline: boolean
}

export interface ActionIn { action: string; text?: string; user_id?: number; outcome?: Outcome; until?: string }

export const useBoard = () => useQuery({ queryKey: ['board'], queryFn: () => api<StickerSummary[]>('board') })
export const useDirectory = () =>
  useQuery({ queryKey: ['directory'], queryFn: () => api<UserBrief[]>('directory/users'), staleTime: 60_000 })
export const useSticker = (id: number | null) =>
  useQuery({ queryKey: ['sticker', id], queryFn: () => api<StickerDetail>(`stickers/${id}`), enabled: id !== null })

/** Refresh every list a sticker can appear in. */
export function useInvalidateStickers() {
  const qc = useQueryClient()
  return (detail?: StickerDetail) => {
    if (detail) qc.setQueryData(['sticker', detail.id], detail)
    for (const k of ['board', 'sent', 'shared', 'archive']) qc.invalidateQueries({ queryKey: [k] })
  }
}

export function useAction(id: number) {
  const refresh = useInvalidateStickers()
  return useMutation({
    mutationFn: (body: ActionIn) => api<StickerDetail>(`stickers/${id}/actions`, { body }),
    onSuccess: (d) => refresh(d),
  })
}

export function useMove() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, quadrant }: { id: number; quadrant: Quadrant }) =>
      api<StickerSummary>(`stickers/${id}/place`, { method: 'PUT', body: { quadrant } }),
    // optimistic: the sticker lands immediately, the server confirms later
    onMutate: async ({ id, quadrant }) => {
      await qc.cancelQueries({ queryKey: ['board'] })
      const prev = qc.getQueryData<StickerSummary[]>(['board'])
      qc.setQueryData<StickerSummary[]>(['board'], (list) =>
        list?.map((s) => (s.id === id ? { ...s, my_quadrant: quadrant, status: s.status === 'new' ? 'triaged' : s.status } : s)),
      )
      return { prev }
    },
    onError: (_e, _v, ctx) => ctx?.prev && qc.setQueryData(['board'], ctx.prev),
    onSettled: (_d, _e, { id }) => {
      qc.invalidateQueries({ queryKey: ['board'] })
      qc.invalidateQueries({ queryKey: ['sticker', id] })
    },
  })
}

export async function uploadFile(stickerId: number, file: File, commentId?: number) {
  const fd = new FormData()
  fd.append('file', file)
  if (commentId) fd.append('comment_id', String(commentId))
  const res = await fetch(`api/stickers/${stickerId}/attachments`, { method: 'POST', body: fd, credentials: 'same-origin' })
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? null)
  return data as Attachment
}

// ---------------------------------------------------------------- looks

/** Small deterministic hash so a sticker keeps its tilt and mount between renders and devices. */
function hash(n: number) {
  let x = Math.imul(n ^ 0x5bd1e995, 0x9e3779b1)
  x ^= x >>> 16
  x = Math.imul(x, 0x85ebca6b)
  x ^= x >>> 13
  x = Math.imul(x, 0xc2b2ae35)
  x ^= x >>> 16
  return x >>> 0
}

const MOUNTS = [
  'tape', 'tape t2', 'tape washi-blue', 'tape washi-mint', 'tape washi-pink', 'corners',
  'pin pin-blue', 'pin pin-yellow', 'pin pin-green', 'pin pin-black', 'pin pin-white', 'pin pin-violet',
  'magnet pin-blue', 'magnet pin-green', 'magnet pin-black', 'magnet pin-violet',
]

export function looks(id: number, overdue: boolean) {
  const h = hash(id)
  // a red pin is reserved for overdue stickers (SPEC: "красная кнопка только у просроченных")
  const mount = overdue ? 'pin pin-red' : MOUNTS[h % MOUNTS.length]
  return { tilt: `r${(h >>> 4) % 7 + 1}`, jitter: `j${(h >>> 8) % 3 + 1}`, mount }
}

export const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).map((p) => p[0]).slice(0, 2).join('').toUpperCase()

export { shortDate, dateTime } from './dates'

export function shortName(name: string) {
  const [first, last] = name.split(/\s+/)
  return last ? `${first} ${last[0]}.` : first
}

export function isoDate(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function addDays(n: number) {
  const d = new Date()
  d.setDate(d.getDate() + n)
  return isoDate(d)
}
