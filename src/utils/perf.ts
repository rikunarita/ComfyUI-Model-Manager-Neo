/**
 * C5 — the permanent performance-mark instrumentation base (Plan §4.8‑C5,
 * K15 "検索 keystroke → 描画 ≤ 16 ms (P95) / 初回グリッド描画 ≤ 1 s").
 *
 * Two halves:
 *
 * 1. **In the browser** — the hot paths (the flat view's filter+sort+chunk
 *    recompute, its painted frame, the initial grid render, the tensor-tree
 *    build) emit `performance.mark` / `performance.measure` entries AND a
 *    sample into a bounded ring buffer. Nothing is recorded unless the
 *    instrumentation is switched on, so the shipping path costs one boolean
 *    test per call site.
 *
 * 2. **Headless** — the same numbers for a 5,000-model synthetic library are
 *    produced by `scripts/bench/front/k15.mjs` (the module is dependency-free
 *    on purpose so the harness can compile and measure it without Vue), and
 *    written to `scripts/bench/results/phase6_front.json` next to the other
 *    KPI evidence (docs/BENCH.md §11).
 *
 * Switching it on (browser console):
 *
 * ```js
 * __mmNeoPerf.enable()   // persists to localStorage; reload not required
 * __mmNeoPerf.summary()  // { name: { count, p50, p95, p99, max } } in ms
 * __mmNeoPerf.reset()    // clear the samples
 * __mmNeoPerf.disable()
 * ```
 *
 * The `performance` entries themselves are visible in the DevTools
 * Performance panel as `mm.*` marks/measures.
 */

/** One recorded duration sample (milliseconds, `performance.now()` base). */
export interface PerfSample {
  name: string
  duration: number
  /** `performance.now()` at recording time (ordering / correlation). */
  at: number
}

/** Percentile summary of one sample name. */
export interface PerfStat {
  count: number
  min: number
  p50: number
  p95: number
  p99: number
  max: number
  mean: number
}

/** The instrumentation marker prefix (DevTools filter: `mm.`). */
export const PERF_PREFIX = 'mm.'

const STORAGE_KEY = 'mmneo.perf'
const GLOBAL_KEY = '__mmNeoPerf'
/** Ring-buffer bound: a long session must not grow without limit. */
const MAX_SAMPLES = 20_000

const samples: PerfSample[] = []
let enabled = false

const hasWindow = typeof window !== 'undefined'
const hasStorage = (() => {
  try {
    return typeof localStorage !== 'undefined'
  } catch {
    return false
  }
})()

const now = (): number =>
  typeof performance !== 'undefined' && typeof performance.now === 'function'
    ? performance.now()
    : Date.now()

const readPersisted = (): boolean => {
  if (!hasStorage) return false
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

const persist = (value: boolean) => {
  if (!hasStorage) return
  try {
    if (value) localStorage.setItem(STORAGE_KEY, '1')
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* private mode / disabled storage: the in-memory flag still works */
  }
}

/** True when marks/measures are being recorded. */
export const perfEnabled = (): boolean => enabled

/** Switch the instrumentation on/off (optionally persisting the choice). */
export const setPerfEnabled = (value: boolean, persistChoice = true): void => {
  enabled = value
  if (persistChoice) persist(value)
}

/** Record one duration sample (a no-op while disabled). */
export const perfRecord = (name: string, duration: number): void => {
  if (!enabled || !Number.isFinite(duration)) return
  samples.push({ name, duration, at: now() })
  if (samples.length > MAX_SAMPLES) samples.splice(0, samples.length - MAX_SAMPLES)
}

/**
 * `performance.mark(name)` (a no-op while disabled). Marks are the anchors of
 * [perfMeasure]; the DevTools Performance panel shows them as `mm.*`.
 */
export const perfMark = (name: string): void => {
  if (!enabled) return
  try {
    performance.mark(name)
  } catch {
    /* environments without the User-Timing API: samples still work */
  }
}

/**
 * `performance.measure(name, startMark, endMark?)` and record its duration as
 * a sample. Returns the measured milliseconds (or `undefined` when the marks
 * are missing / measuring is unsupported).
 */
export const perfMeasure = (
  name: string,
  startMark: string,
  endMark?: string,
): number | undefined => {
  if (!enabled) return undefined
  try {
    const entry = endMark
      ? performance.measure(name, startMark, endMark)
      : performance.measure(name, startMark)
    perfRecord(name, entry.duration)
    return entry.duration
  } catch {
    return undefined
  }
}

/**
 * Time a synchronous block and record it (returns the block's value). Used for
 * the pure-JS phases (filter / sort / chunk / tensor tree) whose cost must be
 * attributable even when no user-timing marks are wanted.
 */
export const perfTime = <T>(name: string, fn: () => T): T => {
  if (!enabled) return fn()
  const start = now()
  try {
    return fn()
  } finally {
    perfRecord(name, now() - start)
  }
}

/** The raw samples (a copy), for the console handle / tests. */
export const perfSamples = (): PerfSample[] => samples.slice()

const percentile = (sorted: number[], p: number): number => {
  if (sorted.length === 0) return 0
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1))
  return sorted[index]
}

/** Per-name percentile summary in milliseconds (K15 reads P95). */
export const perfSummary = (): Record<string, PerfStat> => {
  const byName = new Map<string, number[]>()
  for (const sample of samples) {
    const list = byName.get(sample.name)
    if (list) list.push(sample.duration)
    else byName.set(sample.name, [sample.duration])
  }
  const out: Record<string, PerfStat> = {}
  for (const [name, values] of byName) {
    const sorted = values.slice().sort((a, b) => a - b)
    const total = sorted.reduce((acc, value) => acc + value, 0)
    out[name] = {
      count: sorted.length,
      min: sorted[0],
      p50: percentile(sorted, 50),
      p95: percentile(sorted, 95),
      p99: percentile(sorted, 99),
      max: sorted[sorted.length - 1],
      mean: total / sorted.length,
    }
  }
  return out
}

/** Drop every sample (keeps the enabled flag). */
export const perfReset = (): void => {
  samples.length = 0
  try {
    performance.clearMarks()
    performance.clearMeasures()
  } catch {
    /* nothing to clear */
  }
}

/** The console/debug handle installed on `window` (see the module docs). */
export interface PerfHandle {
  enable: () => void
  disable: () => void
  enabled: () => boolean
  summary: () => Record<string, PerfStat>
  samples: () => PerfSample[]
  reset: () => void
  record: (name: string, duration: number) => void
}

export const perfHandle: PerfHandle = {
  enable: () => setPerfEnabled(true),
  disable: () => setPerfEnabled(false),
  enabled: perfEnabled,
  summary: perfSummary,
  samples: perfSamples,
  reset: perfReset,
  record: perfRecord,
}

if (hasWindow) {
  // Installed unconditionally (the handle is how the switch is reached); the
  // recording itself stays off until enable() / the persisted flag says so.
  ;(window as unknown as Record<string, unknown>)[GLOBAL_KEY] = perfHandle
  if (readPersisted()) setPerfEnabled(true, false)
}
