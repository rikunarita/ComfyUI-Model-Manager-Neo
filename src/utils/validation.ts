import * as v from 'valibot'

export const BaseModelSchema = v.object({
  type: v.string(),
  basename: v.string(),
  extension: v.string(),
  subFolder: v.optional(v.string()),
  pathIndex: v.number(),
  sizeBytes: v.optional(v.number()),
  preview: v.optional(v.union([v.string(), v.array(v.string())])),
  description: v.optional(v.string()),
  metadata: v.optional(v.record(v.string(), v.unknown())),
  createdAt: v.optional(v.number()),
  updatedAt: v.optional(v.number()),
})

export type BaseModel = v.InferOutput<typeof BaseModelSchema>

export const DownloadTaskSchema = v.object({
  taskId: v.string(),
  fullname: v.string(),
  source: v.optional(v.string()),
  downloadedSize: v.optional(v.number()),
  totalSize: v.optional(v.number()),
  bps: v.optional(v.number()),
  preview: v.optional(v.string()),
  error: v.optional(v.string()),
})

export type DownloadTask = v.InferOutput<typeof DownloadTaskSchema>

/** Safely parse an API response, returning null on failure. */
export function safeParse<T>(schema: v.BaseSchema<T, any, any>, data: unknown): T | null {
  const result = v.safeParse(schema, data)
  return result.success ? result.output : null
}
