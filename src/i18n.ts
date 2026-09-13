import { createI18n } from 'vue-i18n'
import { app } from 'scripts/comfyAPI'
import en from './locales/en.json'
import ja from './locales/ja.json'
import zh from './locales/zh.json'

const messages = {
  en: en,
  zh: zh,
  ja: ja,
}

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
