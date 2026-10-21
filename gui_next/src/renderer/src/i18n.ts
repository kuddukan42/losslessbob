import i18next from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './locales/en.json'

// en is the fallback and ships in the main bundle; every other locale is its
// own chunk, fetched when that language is first selected (ensureLanguage).
const LOCALE_LOADERS = import.meta.glob<{ default: Record<string, unknown> }>([
  './locales/*.json', '!./locales/en.json',
])

i18next.use(initReactI18next).init({
  lng: 'en',
  fallbackLng: 'en',
  resources: { en: { translation: en } },
  interpolation: { escapeValue: false },
})

/**
 * Load a locale's bundle if it isn't loaded yet. Resolves (without loading
 * anything) for en or an unknown code — i18next then falls back to en.
 */
export async function ensureLanguage(lng: string): Promise<void> {
  if (i18next.hasResourceBundle(lng, 'translation')) return
  const load = LOCALE_LOADERS[`./locales/${lng}.json`]
  if (!load) return
  const mod = await load()
  i18next.addResourceBundle(lng, 'translation', mod.default)
}

export default i18next
