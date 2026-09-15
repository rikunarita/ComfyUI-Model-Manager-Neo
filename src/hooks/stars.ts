import { reactive } from 'vue'
import { app } from 'scripts/comfyAPI'

/**
 * Star (favourite) marks for models and folders.
 *
 * Persisted through ComfyUI user settings (per user, survives restarts) as
 * two string arrays of the same keys the grids use (`genModelKey`). Module
 * level reactive state keeps every view (grids, cards, detail dialog, bulk
 * bar) in sync without prop drilling.
 */
export const STAR_SETTING_MODELS = 'ModelManager.Stars.Models'
export const STAR_SETTING_FOLDERS = 'ModelManager.Stars.Folders'

export const starState = reactive<{ models: string[]; folders: string[] }>({
  models: [],
  folders: [],
})

/** Read the persisted sets once at startup (App.vue onMounted). */
export const loadStars = () => {
  starState.models = [...(app.ui?.settings.getSettingValue<string[]>(STAR_SETTING_MODELS) ?? [])]
  starState.folders = [...(app.ui?.settings.getSettingValue<string[]>(STAR_SETTING_FOLDERS) ?? [])]
}

const persist = (kind: 'models' | 'folders') => {
  app.ui?.settings.setSettingValue(
    kind === 'models' ? STAR_SETTING_MODELS : STAR_SETTING_FOLDERS,
    starState[kind],
  )
}

const toggleIn = (list: string[], key: string): boolean => {
  const index = list.indexOf(key)
  if (index >= 0) {
    list.splice(index, 1)
    return false
  }
  list.push(key)
  return true
}

export const isModelStarred = (key: string) => starState.models.includes(key)
export const isFolderStarred = (key: string) => starState.folders.includes(key)

export const toggleModelStar = (key: string): boolean => {
  const starred = toggleIn(starState.models, key)
  persist('models')
  return starred
}

export const toggleFolderStar = (key: string): boolean => {
  const starred = toggleIn(starState.folders, key)
  persist('folders')
  return starred
}

/**
 * Bulk-bar star button semantics for a folder selection:
 *  - every selected folder starred  -> unstar all of them;
 *  - mixed or none starred          -> star exactly the unstarred ones,
 *    leaving already-starred folders untouched.
 * Returns true when the selection ends up fully starred.
 */
export const applyFolderStars = (keys: string[]): boolean => {
  const allStarred = keys.length > 0 && keys.every(key => starState.folders.includes(key))
  if (allStarred) {
    for (const key of keys) {
      const index = starState.folders.indexOf(key)
      if (index >= 0) starState.folders.splice(index, 1)
    }
  } else {
    for (const key of keys) {
      if (!starState.folders.includes(key)) starState.folders.push(key)
    }
  }
  persist('folders')
  return !allStarred
}
