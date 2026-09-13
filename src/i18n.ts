import { createI18n, type Composer } from 'vue-i18n'
import { app } from 'scripts/comfyAPI'
import en from './locales/en.json'

/**
 * Optimization B-5: only the locale the session actually uses is fetched.
 *
 * English is bundled statically so the very first paint always has strings;
 * the other bundles are dynamic imports resolved before the app mounts (the
 * files are served from the same origin and cached, so this costs one round
 * trip on a cold cache and nothing afterwards).
 */
const LOADERS: Record<string, () => Promise<{ default: Record<string, unknown> }>> = {
  zh: () => import('./locales/zh.json'),
  ja: () => import('./locales/ja.json'),
}

const messages = { en }

/** Locales this extension ships a complete bundle for. */
const SUPPORTED_LOCALES = ['en', 'zh', 'ja']

/**
 * Reduce a BCP-47 tag to a bundle we actually have.
 *
 * ComfyUI's `Comfy.Locale` and `navigator.language` can both carry region or
 * script subtags (`ja-JP`, `zh-Hant-TW`, `en-GB`). vue-i18n would treat those
 * as unknown locales and log a missing-message warning for every single key, so
 * they are folded onto their base language and anything untranslatable falls
 * back to English explicitly.
 */
const normalizeLocale = (raw: string | undefined | null): string => {
  const base = (raw ?? '').toLowerCase().split(/[-_]/)[0]
  return SUPPORTED_LOCALES.includes(base) ? base : 'en'
}

const getLocalLanguage = () => {
  const configured = app.ui?.settings.getSettingValue<string>('Comfy.Locale')
  if (configured) return normalizeLocale(configured)
  return normalizeLocale(navigator.language)
}

export const i18n = createI18n({
  legacy: false,
  locale: getLocalLanguage(),
  fallbackLocale: 'en',
  messages,
})

const loaded = new Set(['en'])

/** Load the active locale bundle (no-op once present). Safe to await twice. */
export const ensureLocale = async (locale: string): Promise<void> => {
  const loader = LOADERS[locale]
  if (!loader || loaded.has(locale)) return
  const mod = await loader()
  ;(i18n.global as Composer).setLocaleMessage(locale, mod.default)
  loaded.add(locale)
}

// Kick off immediately so the bundle is usually ready before mount; main.ts
// awaits it once more to be sure.
void ensureLocale(i18n.global.locale.value)
