import { reactive } from 'vue'
import { app } from 'scripts/comfyAPI'

/**
 * "Recently used" models: keys recorded when a model is opened in the detail
 * window or added to the node graph. Persisted through ComfyUI user settings
 * (same mechanism as the stars), capped so the list never grows unbounded.
 */
const RECENT_SETTING = 'ModelManager.Recent.Models'
const RECENT_LIMIT = 100

const recentState = reactive<{ entries: { key: string; at: number }[] }>({ entries: [] })

/** Read the persisted list once at startup (App.vue onMounted). */
export const loadRecent = () => {
  const raw = app.ui?.settings.getSettingValue<{ key: string; at: number }[]>(RECENT_SETTING)
  recentState.entries = Array.isArray(raw) ? raw.slice(0, RECENT_LIMIT) : []
}

const persist = () => {
  app.ui?.settings.setSettingValue(RECENT_SETTING, recentState.entries)
}

/** Record a use; most recent first, de-duplicated. */
export const recordRecent = (key: string) => {
  recentState.entries = [
    { key, at: Date.now() },
    ...recentState.entries.filter(entry => entry.key !== key),
  ].slice(0, RECENT_LIMIT)
  persist()
}

/** Last-use timestamp of a model key, or 0 when never used. */
export const recentRank = (key: string): number =>
  recentState.entries.find(entry => entry.key === key)?.at ?? 0
