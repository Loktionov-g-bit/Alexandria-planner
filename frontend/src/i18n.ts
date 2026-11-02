import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import ru from './locales/ru.json'
import en from './locales/en.json'
import be from './locales/be.json'
import kk from './locales/kk.json'
import ka from './locales/ka.json'
import cs from './locales/cs.json'
import de from './locales/de.json'

// Interface languages. Each name is written in its own language, as in the switcher.
export const LANGS = [
  { code: 'ru', name: 'Русский' },
  { code: 'en', name: 'English' },
  { code: 'de', name: 'Deutsch' },
  { code: 'cs', name: 'Čeština' },
  { code: 'be', name: 'Беларуская' },
  { code: 'kk', name: 'Қазақша' },
  { code: 'ka', name: 'ქართული' },
] as const
export type Lang = (typeof LANGS)[number]['code']
const CODES: readonly string[] = LANGS.map((l) => l.code)

const resources = Object.fromEntries(Object.entries({ ru, en, be, kk, ka, cs, de }).map(([k, v]) => [k, { translation: v }]))

const saved = (() => {
  try { return localStorage.getItem('lang') } catch { return null }
})()
const browser = navigator.languages.map((l) => l.slice(0, 2)).find((l) => CODES.includes(l))

i18n.use(initReactI18next).init({
  resources,
  lng: saved && CODES.includes(saved) ? saved : browser ?? 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
  showSupportNotice: false,
})
document.documentElement.lang = i18n.language

export function setLanguage(lng: Lang) {
  i18n.changeLanguage(lng)
  document.documentElement.lang = lng
  document.title = `Alexandria ${i18n.t('app.name')}`
  try { localStorage.setItem('lang', lng) } catch { /* private mode */ }
}

document.title = `Alexandria ${i18n.t('app.name')}`

export default i18n
