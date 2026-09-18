import { reactive } from 'vue'
import { isModelStarred } from 'hooks/stars'
import { app } from 'scripts/comfyAPI'
import { type Model } from 'types/typings'
import { NO_PREVIEW_URL } from 'utils/media'
import { genModelKey } from 'utils/model'

/**
 * Smart collections: saved searches of the flat view, persisted per user in
 * ComfyUI settings (same mechanism as stars / recents). A collection is a
 * plain query object applied as extra AND-constraints on top of the current
 * toolbar filters, so no matching logic is duplicated.
 */
export interface SmartCollectionQuery {
  tokens: string[]
  types: string[]
  minSizeMB?: number
  maxSizeMB?: number
  onlyStarred?: boolean
  onlyNoPreview?: boolean
}

export interface SmartCollection {
  id: string
  name: string
  query: SmartCollectionQuery
}

const COLLECTIONS_SETTING = 'ModelManager.SmartCollections'

export const collectionState = reactive<{
  collections: SmartCollection[]
  activeId: string | null
}>({ collections: [], activeId: null })

/** Read the persisted collections once at startup (App.vue onMounted). */
export const loadCollections = () => {
  const raw = app.ui?.settings.getSettingValue<SmartCollection[]>(COLLECTIONS_SETTING)
  collectionState.collections = Array.isArray(raw) ? raw : []
  collectionState.activeId = null
}

const persist = () => {
  app.ui?.settings.setSettingValue(COLLECTIONS_SETTING, collectionState.collections)
}

export const addCollection = (name: string, query: SmartCollectionQuery) => {
  collectionState.collections = [
    ...collectionState.collections,
    { id: `c-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, name, query },
  ]
  persist()
}

export const removeCollection = (id: string) => {
  collectionState.collections = collectionState.collections.filter(c => c.id !== id)
  if (collectionState.activeId === id) collectionState.activeId = null
  persist()
}

export const activeCollection = (): SmartCollection | undefined =>
  collectionState.collections.find(c => c.id === collectionState.activeId)

/** Extra AND-constraints of a collection against one model. */
export const matchesCollection = (m: Model, q: SmartCollectionQuery): boolean => {
  if (q.types?.length && !q.types.includes(m.type)) return false
  const sizeMB = (m.sizeBytes || 0) / 1024 / 1024
  if (q.minSizeMB != null && sizeMB < q.minSizeMB) return false
  if (q.maxSizeMB != null && sizeMB > q.maxSizeMB) return false
  if (q.onlyStarred && !isModelStarred(genModelKey(m))) return false
  if (q.onlyNoPreview && m.preview !== NO_PREVIEW_URL) return false
  const haystack = `${m.subFolder}/${m.basename}`.toLowerCase()
  for (const token of q.tokens ?? []) {
    if (token && !haystack.includes(token.toLowerCase())) return false
  }
  return true
}
