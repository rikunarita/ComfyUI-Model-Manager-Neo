import yaml from 'yaml'

/**
 * Civitai / HuggingFace / direct-link downloads prepend a YAML front-matter
 * block to the model notes (the `description` field):
 *
 * ```
 * ---
 * author: janxd
 * baseModel: Anima
 * hashes:
 *   AutoV1: 18909B1E
 *   SHA256: 09C4...
 * metadata:
 *   format: SafeTensor
 *   fp: bf16
 *   isRequired: false
 *   size: pruned
 * modelPage: https://civitai.com/models/...
 * preview:
 * - https://image.civitai.com/...
 * website: Civitai
 * ---
 * ```
 *
 * The Information tab renders exactly this block as a table: the known keys
 * with localised labels, `hashes` / `metadata` flattened (their sub-keys keep
 * their own names, except `isRequired` / `size` which are deliberately not
 * shown), `modelPage` / `preview` as links, and every unknown key verbatim at
 * the end of the table.
 */

/** `metadata` sub-keys that must never appear in the Information table. */
const HIDDEN_METADATA_KEYS = new Set(['isRequired', 'size'])

/** `metadata` sub-keys with a localised label; every other stays verbatim. */
const METADATA_LABEL_KEYS = new Set(['format', 'fp'])

/** Top-level keys the parser knows about; everything else is "unknown". */
const KNOWN_TOP_LEVEL_KEYS = new Set([
  'author',
  'baseModel',
  'hashes',
  'metadata',
  'modelPage',
  'preview',
])

export interface InformationRow {
  /** Stable identity for `v-for`. */
  id: string
  /** i18n key under `info.*` for localised labels… */
  labelKey?: string
  /** …or the verbatim key name when the row is shown as-is. */
  labelRaw?: string
  kind: 'text' | 'link' | 'links'
  value?: string
  values?: string[]
}

const FRONTMATTER_RE = /^\uFEFF?---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*\r?\n?/

/**
 * Parse the leading YAML front-matter of a description. Returns `null` when
 * the description carries no (or an unreadable / non-object) block, so the
 * caller can fall back gracefully.
 */
export const parseFrontmatter = (
  description: string | undefined | null,
): Record<string, any> | null => {
  if (!description) return null
  const match = FRONTMATTER_RE.exec(description)
  if (!match) return null
  let parsed: unknown
  try {
    parsed = yaml.parse(match[1])
  } catch {
    return null
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
  return parsed as Record<string, any>
}

/** Every preview URL recorded in the front-matter, in order, de-duplicated. */
export const frontmatterPreviews = (description: string | undefined | null): string[] => {
  const frontmatter = parseFrontmatter(description)
  if (!frontmatter) return []
  return normalizeStringList(frontmatter.preview)
}

const normalizeStringList = (value: unknown): string[] => {
  const list = Array.isArray(value) ? value : value == null ? [] : [value]
  const seen = new Set<string>()
  const result: string[] = []
  for (const item of list) {
    if (typeof item !== 'string') continue
    const url = item.trim()
    if (!url || seen.has(url)) continue
    seen.add(url)
    result.push(url)
  }
  return result
}

const isPlainObject = (value: unknown): value is Record<string, any> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)

/** Scalar (or stringified) rendering for values without a special kind. */
const toText = (value: unknown): string | undefined => {
  if (value == null) return undefined
  if (typeof value === 'string') {
    const text = value.trim()
    return text || undefined
  }
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    const parts = value
      .map(item =>
        isPlainObject(item) || Array.isArray(item) ? JSON.stringify(item) : toText(item),
      )
      .filter((part): part is string => Boolean(part))
    return parts.length ? parts.join(', ') : undefined
  }
  try {
    return JSON.stringify(value)
  } catch {
    return undefined
  }
}

const textRow = (
  id: string,
  label: { key?: string; raw?: string },
  value: unknown,
): InformationRow | null => {
  const text = toText(value)
  if (text === undefined) return null
  return { id, labelKey: label.key, labelRaw: label.raw, kind: 'text', value: text }
}

/**
 * Build the Information-table rows of a description's front-matter.
 *
 * Order: author, baseModel, the flattened `hashes` (sub-key names verbatim),
 * the flattened `metadata` (`format` / `fp` localised, `isRequired` / `size`
 * dropped, other sub-keys verbatim), `modelPage`, `preview` (every URL), and
 * finally all unknown top-level keys verbatim, in their original order.
 */
export const buildInformationRows = (description: string | undefined | null): InformationRow[] => {
  const frontmatter = parseFrontmatter(description)
  if (!frontmatter) return []

  const rows: InformationRow[] = []

  const author = textRow('author', { key: 'info.author' }, frontmatter.author)
  if (author) rows.push(author)

  const baseModel = textRow('baseModel', { key: 'info.baseModel' }, frontmatter.baseModel)
  if (baseModel) rows.push(baseModel)

  // hashes: every entry verbatim (AutoV1 … SHA256_12 and anything else).
  if (isPlainObject(frontmatter.hashes)) {
    for (const [key, value] of Object.entries(frontmatter.hashes)) {
      const row = textRow(`hashes.${key}`, { raw: key }, value)
      if (row) rows.push(row)
    }
  } else {
    const row = textRow('hashes', { raw: 'hashes' }, frontmatter.hashes)
    if (row) rows.push(row)
  }

  // metadata: format / fp localised; isRequired / size never shown; the rest
  // verbatim.
  if (isPlainObject(frontmatter.metadata)) {
    for (const [key, value] of Object.entries(frontmatter.metadata)) {
      if (HIDDEN_METADATA_KEYS.has(key)) continue
      const label = METADATA_LABEL_KEYS.has(key) ? { key: `info.${key}` } : { raw: key }
      const row = textRow(`metadata.${key}`, label, value)
      if (row) rows.push(row)
    }
  } else {
    const row = textRow('metadata', { raw: 'metadata' }, frontmatter.metadata)
    if (row) rows.push(row)
  }

  const modelPage = toText(frontmatter.modelPage)
  if (modelPage) {
    rows.push({
      id: 'modelPage',
      labelKey: 'info.modelPage',
      kind: modelPage.startsWith('http') ? 'link' : 'text',
      value: modelPage,
    })
  }

  const previews = normalizeStringList(frontmatter.preview)
  if (previews.length) {
    rows.push({ id: 'preview', labelKey: 'info.preview', kind: 'links', values: previews })
  }

  // Unknown top-level keys, verbatim, at the end of the table.
  for (const [key, value] of Object.entries(frontmatter)) {
    if (KNOWN_TOP_LEVEL_KEYS.has(key)) continue
    const row = textRow(`unknown.${key}`, { raw: key }, value)
    if (row) rows.push(row)
  }

  return rows
}
