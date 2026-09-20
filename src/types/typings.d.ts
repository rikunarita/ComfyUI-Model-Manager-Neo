export type ContainerSize = { width: number; height: number }
export type ContainerPosition = { left: number; top: number }

/** One tensor entry of a safetensors header (Information tab, Tensor table). */
export interface SafetensorsTensor {
  name: string
  dtype: string
  shape: number[]
}

export interface BaseModel {
  id: number | string
  basename: string
  extension: string
  sizeBytes: number
  type: string
  subFolder: string
  pathIndex: number
  isFolder: boolean
  preview: string | string[]
  description: string
  metadata: Record<string, string>
  /** Exact safetensors tensor layout; only the detail endpoint provides it. */
  tensors?: SafetensorsTensor[]
}

export interface Model extends BaseModel {
  createdAt: number
  updatedAt: number
  children?: Model[]
  /** Model page URL recorded in the notes front-matter (Civitai / HF downloads). */
  modelPage?: string
  /** `website` of the notes front-matter: the model's source platform. */
  modelPlatform?: string
  /** SHA256 recorded in the notes front-matter (duplicate detection). */
  modelSha256?: string
  /** baseModel recorded in the notes front-matter (download base-mismatch warning). */
  modelBase?: string
}

export interface VersionModelFile {
  id: number
  sizeKB: number
  name: string
  type: string
  metadata: Record<string, string>
  hashes: Record<string, string>
  downloadUrl: string
}

export interface VersionModel extends BaseModel {
  shortname: string
  downloadPlatform: string
  downloadUrl: string
  hashes?: Record<string, string>
  files?: VersionModelFile[]
}

/**
 * The editor's resolved payload. `preview` may be a gallery: keeping the
 * "default" source submits every saved preview so a save never deletes the
 * extras (feature: keep all previews).
 */
export type WithResolved<T> = Omit<T, 'preview'> & {
  preview: string | string[] | undefined
}

export type PassThrough<T = void> = T | object | undefined

export interface SelectOptions {
  label: string
  value: any
  icon?: string
  command: () => void
}

export interface DownloadTaskOptions {
  taskId: string
  type: string
  fullname: string
  preview: string
  status: 'pause' | 'waiting' | 'doing'
  progress: number
  downloadedSize: number
  totalSize: number
  bps: number
  error?: string
  source?: 'remote' | 'local'
}

export interface DownloadTask extends Omit<DownloadTaskOptions, 'bps' | 'error'> {
  downloadProgress: string
  downloadSpeed: string
  pauseTask: () => void
  resumeTask: () => void
  deleteTask: () => void
}

export type CustomEventListener = (event: CustomEvent) => void
