/**
 * Search-filter and sort primitives shared by the two grid layouts
 * (Plan §4.8‑C, C1 + C2).
 *
 * Both used to live inline in `DialogManager.vue` / `DialogExplorer.vue`,
 * which cost two things on a large library:
 *
 * - **C1 (regex hoisting)** — the flat view rebuilt one `RegExp` per search
 *   token *per model* inside the filter callback, so a 5,000-model library
 *   compiled the same 1–3 regexes 5,000 times on every keystroke. The tokens
 *   are now compiled ONCE per query ([buildSearchTokens]) and reused for the
 *   whole pass ([filterModels]).
 * - **C2 (collation)** — every `localeCompare` call site now goes through one
 *   of two measured comparators ([compareText] / [compareTextNumeric]). The
 *   numeric variant is the big win: passing options to `localeCompare` makes
 *   V8 rebuild a collator per call (measured 363 ms vs 11.4 ms for a 5,050-name
 *   sort), while for the DEFAULT variant V8's own builtin is faster than a
 *   hoisted `Intl.Collator` - so the two shapes keep different implementations
 *   with identical ordering. Numbers and gates: `scripts/bench/front/k15.mjs`,
 *   docs/BENCH.md §11.
 *
 * The module is deliberately dependency-free (no Vue, no component imports) so
 * the headless K15 harness (`scripts/bench/front/k15.mjs`) can compile and
 * measure the very same code the browser runs — Plan §4.8‑C5 "計測基盤".
 */

/** One whitespace-separated search token together with its compiled matcher. */
export interface SearchToken {
  /** The token exactly as typed (diagnostics only). */
  raw: string
  /** Case-insensitive matcher; `*` acts as a wildcard, every other regex
   *  special is escaped literally. */
  regex: RegExp
}

/** The minimum shape the grid pipeline needs of a listing entry. */
export interface GridModel {
  isFolder: boolean
  subFolder: string
  basename: string
}

/** One rendered grid row (the virtual scroller's item). */
export interface GridRow<T> {
  /** Stable row identity: the joined keys of its models. */
  key: string
  row: T[]
}

/** `\s+` — the token splitter (hoisted: stateless, so one instance is safe). */
const TOKEN_SPLIT_RE = /\s+/
/** Regex metacharacters that must be escaped before `*` is restored. */
const REGEX_SPECIAL_RE = /[.*+?^${}()|[\]\\]/g
/** The escaped form of `*` produced by the step above. */
const ESCAPED_STAR_RE = /\\\*/g

/**
 * Compile one search token into a case-insensitive matcher.
 *
 * Semantics are the historical ones of the flat view: every regex special is
 * escaped (so `sd(1.5)` searches literally) and `*` is then restored as a
 * `.*` wildcard (so `*xl*` keeps working). A pattern that somehow fails to
 * compile falls back to the raw token, exactly as before.
 */
const buildTokenRegex = (raw: string): RegExp => {
  try {
    const escaped = raw.replace(REGEX_SPECIAL_RE, '\\$&').replace(ESCAPED_STAR_RE, '.*')
    return new RegExp(escaped, 'i')
  } catch {
    return new RegExp(raw, 'i')
  }
}

/**
 * Split a query into tokens and compile each ONCE (C1).
 *
 * Call this outside the per-model loop (a `computed`, or once per filter pass)
 * and hand the result to [filterModels]; an empty/blank query yields `[]`,
 * which matches everything.
 */
export const buildSearchTokens = (query: string | null | undefined): SearchToken[] => {
  const raw = query ?? ''
  if (!raw.trim()) return []
  return raw
    .split(TOKEN_SPLIT_RE)
    .filter(Boolean)
    .map(token => ({ raw: token, regex: buildTokenRegex(token) }))
}

/**
 * True when EVERY token matches at least one of `fields` (an empty token list
 * matches everything). `null`/`undefined` fields are skipped, so a caller can
 * pass `subFolder` and `basename` without normalising them first.
 */
const tokensMatch = (tokens: SearchToken[], fields: (string | null | undefined)[]): boolean => {
  if (tokens.length === 0) return true
  return tokens.every(token =>
    fields.some(field => typeof field === 'string' && token.regex.test(field)),
  )
}

/**
 * The flat view's filter pass: drop folders, keep every model whose
 * folder/name matches all tokens AND that passes the caller's extra gate (the
 * model-type and smart-collection checks stay in the component — they read
 * stores this module must not know about).
 */
const filterModels = <T extends GridModel>(
  models: T[],
  tokens: SearchToken[],
  matches?: (model: T) => boolean,
): T[] => {
  const keepToken = tokens.length > 0
  const out: T[] = []
  for (const model of models) {
    if (model.isFolder) continue
    if (matches && !matches(model)) continue
    if (keepToken && !tokensMatch(tokens, [model.subFolder, model.basename])) continue
    out.push(model)
  }
  return out
}

/**
 * Split a sorted listing into fixed-width rows (the virtual scroller renders
 * one row per item). Returns `[]` for a non-positive width, mirroring the
 * guard the component kept for es-toolkit's `chunk()` (which throws there).
 */
const chunkRows = <T>(list: T[], columns: number, keyOf: (model: T) => string): GridRow<T>[] => {
  if (columns < 1) return []
  const rows: GridRow<T>[] = []
  for (let start = 0; start < list.length; start += columns) {
    const row = list.slice(start, start + columns)
    rows.push({ key: row.map(keyOf).join(','), row })
  }
  return rows
}

/**
 * The flat grid's whole row pipeline — filter → sort → chunk — as one pure
 * function so the component and the K15 harness measure identical code.
 *
 * `compare` receives two models and returns their order (the component passes
 * its star-first + chosen-sort-order comparator); the sort is applied to the
 * filtered copy, never to the caller's array.
 */
export const buildModelRows = <T extends GridModel>(
  models: T[],
  options: {
    tokens: SearchToken[]
    matches?: (model: T) => boolean
    compare: (a: T, b: T) => number
    columns: number
    keyOf: (model: T) => string
  },
): GridRow<T>[] => {
  const filtered = filterModels(models, options.tokens, options.matches)
  filtered.sort(options.compare)
  return chunkRows(filtered, options.columns, options.keyOf)
}

/**
 * Comparators (C2) — chosen by MEASUREMENT, not by intuition
 * (`scripts/bench/front/k15.mjs`, docs/BENCH.md §11).
 *
 * Sorting 5,050 model names on this repository's V8 (Node 20 / Chrome's engine)
 * measured:
 *
 * | comparator                                  | p50     |
 * | ------------------------------------------- | ------- |
 * | `a.localeCompare(b)`                        | 2.56 ms |
 * | hoisted `new Intl.Collator().compare`       | 8.09 ms |
 * | `a.localeCompare(b, undefined, {numeric})`  | 363 ms  |
 * | hoisted numeric `Intl.Collator().compare`   | 11.4 ms |
 *
 * So the Plan's C2 hypothesis holds spectacularly for the NUMERIC variant
 * (V8 has no fast path when options are passed, so every call rebuilt a
 * collator: 32x) but is **inverted for the default variant**: V8 caches the
 * default collator inside `localeCompare` and its builtin beats the public
 * `Intl.Collator` API by ~3x. Both facts are pinned by the bench's gates, and
 * the two call shapes therefore get the two different implementations below —
 * same semantics, same ordering, fastest measured code path for each.
 */
const numericCollator = new Intl.Collator(undefined, { numeric: true })
/** Hoisted once: `compare` is a getter returning a bound function, and going
 *  through the instance per comparison measured ~10% slower. */
const numericCompare = numericCollator.compare

/**
 * Default-variant text compare (`a.localeCompare(b)` semantics: default
 * locale, default options).
 */
export const compareText = (a: string, b: string): number => a.localeCompare(b)

/** `a.localeCompare(b, undefined, { numeric: true })` semantics through the
 *  hoisted collator: embedded digit runs compare as numbers (`layer2` before
 *  `layer10`) at ~1/32 of the per-call cost. */
const compareTextNumeric = (a: string, b: string): number => numericCompare(a, b)

/**
 * Natural order for tree segments (the tensor tree's historical rule): a
 * segment pair that is *entirely* numeric compares as numbers (`2` before
 * `19`), everything else falls back to the numeric-aware collator so `layer2`
 * still precedes `layer10`.
 */
export const naturalCompare = (a: string, b: string): number => {
  const an = Number(a)
  const bn = Number(b)
  if (a.trim() !== '' && b.trim() !== '' && Number.isFinite(an) && Number.isFinite(bn)) {
    if (an !== bn) return an - bn
    return compareText(a, b)
  }
  return compareTextNumeric(a, b)
}
