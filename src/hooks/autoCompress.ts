import { type SingleCompressItem, queueSingleCompress } from 'hooks/zipnn'
import { app } from 'scripts/comfyAPI'
import { type Model } from 'types/typings'
import { genModelKey } from 'utils/model'

const fullnameOf = (m: Model) =>
  `${m.subFolder ? `${m.subFolder}/` : ''}${m.basename}${m.extension}`

/** Compressible: plain .safetensors, not already compressed. */
const compressible = (m: Model) =>
  !m.isFolder && m.extension === '.safetensors' && !m.basename.endsWith('.znn')

/**
 * Setting-driven auto compression of models untouched for N days
 * (`ModelManager.Zipnn.AutoCompressUnusedDays`, 0 = off). "Unused" is proxied
 * by the file mtime, which is the only evidence available without a runtime
 * agent; the queue runs sequentially behind any manual task.
 */
export const autoCompressUnused = (data: Record<string, Model[]>) => {
  const days = Number(
    app.ui?.settings.getSettingValue('ModelManager.Zipnn.AutoCompressUnusedDays') ?? 0,
  )
  if (!(days > 0)) return
  const cutoff = Date.now() - days * 86_400_000
  const items: SingleCompressItem[] = []
  for (const [type, list] of Object.entries(data)) {
    for (const m of list) {
      if (!compressible(m)) continue
      if ((m.updatedAt ?? 0) >= cutoff) continue
      items.push({ type, pathIndex: m.pathIndex, fullname: fullnameOf(m), key: genModelKey(m) })
    }
  }
  if (items.length) queueSingleCompress(items)
}

/**
 * Setting-driven compression right after a download completes
 * (`ModelManager.Zipnn.AutoCompressOnDownload`). The refreshed folder listing
 * supplies the model entry (pathIndex / key).
 */
export const autoCompressDownloaded = (type: string, fullname: string, list: Model[]) => {
  const on =
    app.ui?.settings.getSettingValue<boolean>('ModelManager.Zipnn.AutoCompressOnDownload') ?? false
  if (!on) return
  const base = fullname.split('/').pop() ?? ''
  if (!base.endsWith('.safetensors') || base.endsWith('.znn.safetensors')) return
  const model = list.find(m => !m.isFolder && fullnameOf(m) === fullname)
  if (!model) return
  queueSingleCompress([{ type, pathIndex: model.pathIndex, fullname, key: genModelKey(model) }])
}
