import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api, ApiError, type Me } from './api'
import { setLanguage } from './i18n'

export function useMe() {
  return useQuery<Me | null>({
    queryKey: ['me'],
    queryFn: async () => {
      try {
        return await api<Me>('auth/me')
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null
        throw e
      }
    },
  })
}

export function useSetMe() {
  const qc = useQueryClient()
  return (me: Me | null) => qc.setQueryData(['me'], me)
}

/** Apply the user's theme and language preferences. */
export function usePreferences(me: Me | null | undefined) {
  const theme = me?.user.theme
  const locale = me?.user.locale
  useEffect(() => {
    const root = document.documentElement
    if (!theme || theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
  }, [theme])
  useEffect(() => {
    if (locale) setLanguage(locale)
  }, [locale])
}

export function errorText(t: (k: string) => string, e: unknown): string {
  if (e instanceof ApiError) return e.keys.map((k) => t(k)).join(' ')
  return t('error.generic')
}
