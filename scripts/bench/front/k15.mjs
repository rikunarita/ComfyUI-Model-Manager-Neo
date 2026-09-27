#!/usr/bin/env node
/**
 * K15 / Phase 6 frontend bench (Plan §4.8‑C5 "performance mark 計測基盤",
 * §2.2 K15, §6.2 Phase 6 完了条件).
 *
 * Measures the REAL browser code path headlessly: the pure modules under
 * `src/utils` are compiled with the repository's own TypeScript and then driven
 * with a deterministic 5,000-model synthetic library (the same scale the Plan's
 * K15 names) and a DeepSeek-shaped 65k-tensor MoE header.
 *
 * What is measured, and why it is comparable across machines:
 *
 *  - **C1** the flat view's filter pass with the token regexes rebuilt per
 *    model (the pre-Phase-6 code, inlined here verbatim as `naive*`) against
 *    the hoisted `buildSearchTokens` + `buildModelRows` path;
 *  - **C2** the same sort with `String#localeCompare` against the shared
 *    `Intl.Collator`;
 *  - **K15 keystroke** the whole `buildModelRows` pipeline (filter → sort →
 *    chunk) per keystroke over 200 queries — this is the JS work that has to
 *    fit a 16 ms frame; the browser-side paint leg is instrumented separately
 *    by `src/utils/perf.ts` (`__mmNeoPerf.summary()` → `mm.grid.queryToPaint`),
 *    which a headless run cannot reproduce;
 *  - **K15 initial grid** the first (query-less) row build over all 5,000;
 *  - **tensor tree** the pre-Phase-6 in-browser fold (verbatim), the same fold
 *    with shared collators, and the Phase-6 path: decode the Rust payload into
 *    the lazy index (`createTensorTreeIndex`) + render the collapsed rows.
 *
 * The GATES are same-run ratios (before vs after on one machine), so they are
 * meaningful on any runner; the absolute numbers are recorded with the `env`
 * block exactly like the other benches in this suite.
 *
 * Usage:
 *   node scripts/bench/front/k15.mjs [--models 5000] [--keystrokes 200]
 *        [--json-out scripts/bench/results/phase6_front.json] [--cross-check]
 *
 * `--cross-check` additionally verifies that the JS fallback encoder produces
 * the SAME document as the Rust `mm_core.safetensors_tensor_tree` (needs
 * python3 + a built native binary; skipped with a note otherwise).
 */

import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(HERE, '../../..')
const RESULTS = path.join(REPO_ROOT, 'scripts/bench/results')

// ---------------------------------------------------------------------------
// arguments
// ---------------------------------------------------------------------------
const argv = process.argv.slice(2)
const argOf = (name, fallback) => {
  const at = argv.indexOf(`--${name}`)
  return at >= 0 && argv[at + 1] !== undefined ? argv[at + 1] : fallback
}
const MODELS = Number(argOf('models', 5000))
const KEYSTROKES = Number(argOf('keystrokes', 200))
const COLUMNS = Number(argOf('columns', 6))
const MOE_LAYERS = Number(argOf('moe-layers', 84))
const MOE_EXPERTS = Number(argOf('moe-experts', 256))
const JSON_OUT = argOf('json-out', path.join(RESULTS, 'phase6_front.json'))
const CROSS_CHECK = argv.includes('--cross-check')

// ---------------------------------------------------------------------------
// compile the pure TS modules with the repository's own tsc
// ---------------------------------------------------------------------------
// The repository's own TypeScript, overridable for CI cells that install it
// outside the pnpm store (native.yml's integration job).
const TSC = process.env.MMNEO_TSC || path.join(REPO_ROOT, 'node_modules/typescript/bin/tsc')
if (!fs.existsSync(TSC)) {
  console.error(
    `typescript not found at ${TSC} - run \`pnpm install --frozen-lockfile\` (or set MMNEO_TSC)`,
  )
  process.exit(2)
}
const OUT = fs.mkdtempSync(path.join(os.tmpdir(), 'mmneo-k15-'))
const SOURCES = ['src/utils/modelFilter.ts', 'src/utils/tensorTree.ts', 'src/utils/perf.ts']
// `paths` are resolved relative to the tsconfig's own directory (TypeScript 6
// deprecated `baseUrl`), so the aliases are spelled relative to OUT.
const REL = path.relative(OUT, REPO_ROOT).split(path.sep).join('/')
const tsconfig = {
  compilerOptions: {
    target: 'ES2022',
    module: 'ESNext',
    moduleResolution: 'bundler',
    strict: true,
    skipLibCheck: true,
    types: [],
    outDir: OUT,
    rootDir: REPO_ROOT,
    paths: { 'utils/*': [`${REL}/src/utils/*`], 'types/*': [`${REL}/src/types/*`] },
  },
  files: SOURCES.map(rel => path.join(REPO_ROOT, rel)),
}
const tsconfigPath = path.join(OUT, 'tsconfig.json')
fs.writeFileSync(tsconfigPath, JSON.stringify(tsconfig, null, 2))
const tsc = spawnSync(process.execPath, [TSC, '-p', tsconfigPath], { encoding: 'utf8' })
if (tsc.status !== 0) {
  console.error('tsc failed:\n' + (tsc.stdout || '') + (tsc.stderr || ''))
  process.exit(2)
}
// The emitted JS keeps the tsconfig path aliases (`utils/modelFilter`), which
// Node cannot resolve; rewrite them to the sibling files tsc just emitted.
const emitDir = path.join(OUT, 'src/utils')
for (const file of fs.readdirSync(emitDir)) {
  if (!file.endsWith('.js')) continue
  const target = path.join(emitDir, file)
  const code = fs
    .readFileSync(target, 'utf8')
    .replace(/from 'utils\/(\w+)'/g, "from './$1.js'")
    .replace(/from 'types\/(\w+)'/g, "from './$1.js'")
  fs.writeFileSync(target, code)
}
const modelFilter = await import(path.join(emitDir, 'modelFilter.js'))
const tensorTree = await import(path.join(emitDir, 'tensorTree.js'))
const { buildSearchTokens, buildModelRows, compareText } = modelFilter
const { buildTensorTreePayload, createTensorTreeIndex, tensorParams } = tensorTree

// ---------------------------------------------------------------------------
// deterministic synthetic library (5,000 models) + MoE header (65k tensors)
// ---------------------------------------------------------------------------
const rng = seed => {
  let state = seed >>> 0
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0
    return state / 0x100000000
  }
}

const TYPES = ['checkpoints', 'loras', 'vae', 'controlnet', 'embeddings', 'upscale_models']
const WORDS = [
  'dreamshaper',
  'realistic',
  'anime',
  'pony',
  'flux',
  'sdxl',
  'base',
  'inpainting',
  'lora',
  'detail',
  'style',
  'v2',
  'xl',
  'turbo',
  'lightning',
  'fp16',
  'pruned',
]

const makeModels = count => {
  const rand = rng(20260927)
  const models = []
  for (let i = 0; i < count; i++) {
    const type = TYPES[Math.floor(rand() * TYPES.length)]
    const words = 1 + Math.floor(rand() * 3)
    const parts = []
    for (let w = 0; w < words; w++) parts.push(WORDS[Math.floor(rand() * WORDS.length)])
    const basename = `${parts.join('_')}_${i}`
    const depth = rand() < 0.25 ? 1 + Math.floor(rand() * 2) : 0
    const subFolder = Array.from(
      { length: depth },
      (_, d) => `pack_${d}_${Math.floor(rand() * 40)}`,
    ).join('/')
    models.push({
      type,
      subFolder,
      isFolder: false,
      basename,
      extension: '.safetensors',
      pathIndex: 0,
      sizeBytes: Math.floor(rand() * 7e9),
      createdAt: 1.7e12 + Math.floor(rand() * 1e10),
      updatedAt: 1.7e12 + Math.floor(rand() * 1e10),
      preview: '/model-manager/no-preview.svg',
    })
  }
  // a handful of folders, like a real listing carries
  for (let i = 0; i < Math.max(1, Math.floor(count / 100)); i++) {
    models.push({
      type: TYPES[i % TYPES.length],
      subFolder: '',
      isFolder: true,
      basename: `pack_${i}`,
      extension: '',
      pathIndex: 0,
      sizeBytes: 0,
      createdAt: 1.7e12,
      updatedAt: 1.7e12,
      preview: null,
    })
  }
  return models
}

const makeMoeTensors = (layers, experts) => {
  const tensors = []
  const attention = [
    'self_attn.q_proj.weight',
    'self_attn.k_proj.weight',
    'self_attn.v_proj.weight',
    'self_attn.o_proj.weight',
    'mlp.gate.weight',
    'mlp.shared_experts.gate_proj.weight',
    'mlp.shared_experts.up_proj.weight',
    'mlp.shared_experts.down_proj.weight',
    'input_layernorm.weight',
  ]
  for (let layer = 0; layer < layers; layer++) {
    for (const name of attention) {
      tensors.push({ name: `model.layers.${layer}.${name}`, dtype: 'BF16', shape: [7168, 16384] })
    }
    for (let expert = 0; expert < experts; expert++) {
      for (const proj of ['gate_proj', 'up_proj', 'down_proj']) {
        tensors.push({
          name: `model.layers.${layer}.mlp.experts.${expert}.${proj}.weight`,
          dtype: 'BF16',
          shape: [2048, 7168],
        })
      }
    }
  }
  return tensors
}

const models = makeModels(MODELS)
const keyOf = model =>
  `${model.type}:${model.pathIndex}:${model.subFolder}:${model.basename}${model.extension}`
const moeTensors = makeMoeTensors(MOE_LAYERS, MOE_EXPERTS)

// ---------------------------------------------------------------------------
// the pre-Phase-6 implementations, verbatim (the "before" side of every gate)
// ---------------------------------------------------------------------------
/** DialogManager.vue's `list` computed before C1/C2 (regex rebuilt per model,
 *  `String#localeCompare` per comparison, es-toolkit `chunk`). */
const naiveBuildRows = (allModels, rawFilter, cols, starred) => {
  const mergedList = allModels
  const pureModels = mergedList.filter(item => !item.isFolder)

  function buildRegex(raw) {
    try {
      const escaped = raw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\\\*/g, '.*')
      return new RegExp(escaped, 'i')
    } catch {
      return new RegExp(raw, 'i')
    }
  }

  const filterList = pureModels.filter(model => {
    const tokens = rawFilter.split(/\s+/).filter(Boolean)
    const regexes = tokens.map(buildRegex)
    return regexes.every(re => re.test(model.subFolder) || re.test(model.basename))
  })

  const sortStrategy = (a, b) => a.basename.localeCompare(b.basename)
  const sortedList = filterList.sort((a, b) => {
    const byStar = Number(starred(b)) - Number(starred(a))
    return byStar || sortStrategy(a, b)
  })
  if (cols < 1) return []
  const rows = []
  for (let i = 0; i < sortedList.length; i += cols) {
    const row = sortedList.slice(i, i + cols)
    rows.push({ key: row.map(keyOf).join(','), row })
  }
  return rows
}

/** ModelInformation.vue's `tensorTree` computed before Phase 6. */
const legacyTensorTree = tensors => {
  const root = { segment: '', path: '', children: [], tensors: [], totalCount: 0, totalParams: 0 }
  const nodes = new Map()
  for (const tensor of tensors) {
    const segments = (tensor.name ?? '').split('.')
    let parent = root
    let path = ''
    for (let i = 0; i < segments.length - 1; i++) {
      const segment = segments[i] || '(unnamed)'
      path = path ? `${path}.${segment}` : segment
      let node = nodes.get(path)
      if (!node) {
        node = { segment, path, children: [], tensors: [], totalCount: 0, totalParams: 0 }
        nodes.set(path, node)
        parent.children.push(node)
      }
      parent = node
    }
    parent.tensors.push(tensor)
  }
  const paramsOf = list =>
    list.reduce((total, t) => total + (t.shape ?? []).reduce((acc, dim) => acc * dim, 1), 0)
  const aggregate = node => {
    let count = node.tensors.length
    let params = paramsOf(node.tensors)
    for (const child of node.children) {
      const [cc, cp] = aggregate(child)
      count += cc
      params += cp
    }
    node.totalCount = count
    node.totalParams = params
    return [count, params]
  }
  const naturalCompare = (a, b) => {
    const an = Number(a)
    const bn = Number(b)
    if (a.trim() !== '' && b.trim() !== '' && Number.isFinite(an) && Number.isFinite(bn)) {
      if (an !== bn) return an - bn
      return a.localeCompare(b)
    }
    return a.localeCompare(b, undefined, { numeric: true })
  }
  const tail = (node, t) =>
    node.path ? (t.name ?? '').slice(node.path.length + 1) : (t.name ?? '')
  const sortChildren = node => {
    node.children.sort((a, b) => naturalCompare(a.segment, b.segment))
    node.tensors.sort((a, b) => naturalCompare(tail(node, a), tail(node, b)))
    node.children.forEach(sortChildren)
  }
  aggregate(root)
  sortChildren(root)
  return root
}

/** The Phase-6 renderer's row walk over the lazy index (collapsed tree). */
const renderRows = (index, expanded = new Set()) => {
  const rows = []
  const walk = (nodeIndex, nodePath, depth) => {
    for (const childIndex of index.childrenOf(nodeIndex)) {
      const childPath = index.pathOf(childIndex, nodePath)
      const view = index.viewOf(childIndex, nodePath)
      rows.push({ key: `f:${childPath}`, kind: 'folder', depth, ...view })
      if (expanded.has(childPath)) walk(childIndex, childPath, depth + 1)
    }
    const leaves = index.tensorsOf(nodeIndex, nodePath)
    for (const tensor of leaves.slice(0, 500)) rows.push({ kind: 'leaf', tensor })
  }
  walk(0, '', 0)
  return rows
}

// ---------------------------------------------------------------------------
// measurement plumbing
// ---------------------------------------------------------------------------
const stats = samples => {
  const sorted = samples.slice().sort((a, b) => a - b)
  const at = p =>
    sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1))]
  const total = sorted.reduce((acc, v) => acc + v, 0)
  return {
    count: sorted.length,
    min: sorted[0],
    p50: at(50),
    p95: at(95),
    p99: at(99),
    max: sorted[sorted.length - 1],
    mean: total / sorted.length,
  }
}

const timeIt = (reps, fn) => {
  fn(0) // warm-up (JIT + ICU init) - the same call shape as the measured reps
  const samples = []
  for (let i = 0; i < reps; i++) {
    const t0 = performance.now()
    fn(i)
    samples.push(performance.now() - t0)
  }
  return stats(samples)
}

const QUERIES = (() => {
  const rand = rng(7)
  const list = []
  for (let i = 0; i < KEYSTROKES; i++) {
    const tokens = 1 + Math.floor(rand() * 2)
    const parts = []
    for (let t = 0; t < tokens; t++) {
      const word = WORDS[Math.floor(rand() * WORDS.length)]
      // a realistic keystroke stream: growing prefixes plus the odd wildcard
      parts.push(
        rand() < 0.15
          ? `${word.slice(0, 2)}*`
          : word.slice(0, 1 + Math.floor(rand() * word.length)),
      )
    }
    list.push(parts.join(' '))
  }
  return list
})()

const neverStarred = () => false

// ---------------------------------------------------------------------------
// run
// ---------------------------------------------------------------------------
console.log(`== k15 front bench: ${models.length} models, ${moeTensors.length} MoE tensors ==`)

const grid = {}

grid.keystrokeNaive = timeIt(KEYSTROKES, i =>
  naiveBuildRows(models, QUERIES[i], COLUMNS, neverStarred),
)
grid.keystrokeHoisted = timeIt(KEYSTROKES, i => {
  const tokens = buildSearchTokens(QUERIES[i])
  return buildModelRows(models, {
    tokens,
    compare: (a, b) => compareText(a.basename, b.basename),
    columns: COLUMNS,
    keyOf,
  })
})
// isolate C2: the same hoisted pipeline, but sorting with localeCompare
grid.keystrokeHoistedLocaleSort = timeIt(KEYSTROKES, i => {
  const tokens = buildSearchTokens(QUERIES[i])
  return buildModelRows(models, {
    tokens,
    compare: (a, b) => a.basename.localeCompare(b.basename),
    columns: COLUMNS,
    keyOf,
  })
})
grid.initialRenderNaive = timeIt(20, () => naiveBuildRows(models, '', COLUMNS, neverStarred))
grid.initialRenderHoisted = timeIt(20, () =>
  buildModelRows(models, {
    tokens: buildSearchTokens(''),
    compare: (a, b) => compareText(a.basename, b.basename),
    columns: COLUMNS,
    keyOf,
  }),
)

// C2: the numeric variant (the tensor tree's segments) is where hoisting a
// collator pays - V8 has no fast path once options are passed to localeCompare.
const SEGMENTS = (() => {
  const list = []
  for (let i = 0; i < 3000; i++) list.push(String((i * 7919) % 1000))
  for (const w of [
    'gate_proj',
    'up_proj',
    'down_proj',
    'self_attn',
    'mlp',
    'experts',
    'layer10',
    'layer2',
  ])
    for (let i = 0; i < 200; i++) list.push(`${w}${i % 17}`)
  return list
})()
const numericCollator = new Intl.Collator(undefined, { numeric: true })
const hoistedNumeric = numericCollator.compare
grid.numericLocaleCompare = timeIt(9, () =>
  SEGMENTS.slice().sort((a, b) => a.localeCompare(b, undefined, { numeric: true })),
)
grid.numericHoistedCollator = timeIt(9, () => SEGMENTS.slice().sort(hoistedNumeric))
const defaultCollator = new Intl.Collator()
const hoistedDefault = defaultCollator.compare
grid.defaultLocaleCompare = timeIt(9, () => SEGMENTS.slice().sort((a, b) => a.localeCompare(b)))
grid.defaultHoistedCollator = timeIt(9, () => SEGMENTS.slice().sort(hoistedDefault))

// parity: the two implementations must produce the SAME rows
const sampleQuery = QUERIES[3]
const naiveRows = naiveBuildRows(models, sampleQuery, COLUMNS, neverStarred)
const hoistedRows = buildModelRows(models, {
  tokens: buildSearchTokens(sampleQuery),
  compare: (a, b) => compareText(a.basename, b.basename),
  columns: COLUMNS,
  keyOf,
})
const sameRows =
  naiveRows.length === hoistedRows.length &&
  naiveRows.every((row, i) => row.key === hoistedRows[i].key)
if (!sameRows) {
  console.error('GATE FAIL: the hoisted pipeline changed the rendered rows')
  process.exit(1)
}

const tree = {}
tree.legacyFold = timeIt(3, () => legacyTensorTree(moeTensors))
tree.payloadBuild = timeIt(3, () => buildTensorTreePayload(moeTensors))
const payload = buildTensorTreePayload(moeTensors)
tree.payloadBytes = JSON.stringify(payload).length
tree.payloadNodes = payload.nodes.length
const parsed = JSON.parse(JSON.stringify(payload))
tree.indexCreate = timeIt(5, () => createTensorTreeIndex(parsed, moeTensors))
tree.renderCollapsed = timeIt(20, () => renderRows(createTensorTreeIndex(parsed, moeTensors)))
// the legacy renderer's row walk over the nested tree (collapsed) for reference
tree.legacyRenderCollapsed = timeIt(5, () => {
  const built = legacyTensorTree(moeTensors)
  const rows = []
  const walk = (node, depth) => {
    for (const child of node.children) {
      rows.push({ key: `f:${child.path}`, depth })
      // collapsed: do not descend
    }
    for (const t of node.tensors.slice(0, 500)) rows.push({ key: `t:${t.name}`, depth })
  }
  walk(built, 0)
  return rows
})
// the fallback path (no Rust payload): JS fold -> index -> render
tree.fallbackPath = timeIt(3, () => {
  const built = buildTensorTreePayload(moeTensors)
  const index = createTensorTreeIndex(built, moeTensors)
  return renderRows(index)
})

// ---------------------------------------------------------------------------
// the payload validator: a hostile/stale/inconsistent tree must be REJECTED
// (the component then folds the tree itself) instead of rendering a wrong
// table. TypeScript has no unit-test runner in this repository, so the decoder's
// defensive branch is gated here - in the same harness CI already runs.
// ---------------------------------------------------------------------------
const validatorCases = (() => {
  const small = [
    { name: 'a.b.w', dtype: 'BF16', shape: [2, 2] },
    { name: 'a.c', dtype: 'BF16', shape: [3] },
    { name: 'top', dtype: 'F32', shape: [] },
  ]
  const good = buildTensorTreePayload(small)
  const clone = () => JSON.parse(JSON.stringify(good))
  const cases = {
    acceptsTheRealPayload: () => createTensorTreeIndex(clone(), small) !== null,
    rejectsNull: () => createTensorTreeIndex(null, small) === null,
    rejectsANonObject: () => createTensorTreeIndex('nope', small) === null,
    rejectsAWrongVersion: () => {
      const bad = clone()
      bad.v = 2
      return createTensorTreeIndex(bad, small) === null
    },
    rejectsMissingArrays: () => {
      const bad = clone()
      delete bad.leaves
      return createTensorTreeIndex(bad, small) === null
    },
    rejectsANodeTupleOfTheWrongShape: () => {
      const bad = clone()
      bad.nodes[1] = ['a', 1, 0, 9]
      return createTensorTreeIndex(bad, small) === null
    },
    rejectsANonStringSegment: () => {
      const bad = clone()
      bad.nodes[1][0] = 7
      return createTensorTreeIndex(bad, small) === null
    },
    rejectsANegativeOrNonFiniteCount: () => {
      const neg = clone()
      neg.nodes[1][2] = -1
      const nan = clone()
      nan.nodes[1][3] = Number.NaN
      return (
        createTensorTreeIndex(neg, small) === null && createTensorTreeIndex(nan, small) === null
      )
    },
    rejectsALeafIndexOutsideTheTensorList: () => {
      const bad = clone()
      bad.leaves[0] = small.length + 5
      return createTensorTreeIndex(bad, small) === null
    },
    rejectsANonIntegerLeaf: () => {
      const bad = clone()
      bad.leaves[0] = 1.5
      return createTensorTreeIndex(bad, small) === null
    },
    rejectsInconsistentOwnCounts: () => {
      const bad = clone()
      bad.nodes[0][2] = bad.nodes[0][2] + 1 // sum(own) != leaves.length
      return createTensorTreeIndex(bad, small) === null
    },
    rejectsABrokenPreOrderStructure: () => {
      const bad = clone()
      bad.nodes[0][1] = bad.nodes[0][1] + 1 // a child that does not exist
      return createTensorTreeIndex(bad, small) === null
    },
    rejectsAnEmptyNodeTable: () =>
      createTensorTreeIndex({ v: 1, nodes: [], leaves: [] }, []) === null,
    // the stale-payload guard: `tensors` and the tree come from two separate
    // header parses server-side, so a file replaced in between must be caught
    rejectsATreeForADifferentTensorList: () => {
      const other = buildTensorTreePayload(
        small.concat([{ name: 'x.y', dtype: 'F32', shape: [1] }]),
      )
      return createTensorTreeIndex(other, small) === null
    },
    acceptsAnEmptyHeader: () => {
      const index = createTensorTreeIndex(buildTensorTreePayload([]), [])
      return index !== null && index.size === 1 && index.rootCount === 0 && index.rootParams === 0
    },
  }
  const out = {}
  for (const [name, run] of Object.entries(cases)) out[name] = run()
  return out
})()
const validatorFailed = Object.entries(validatorCases).filter(([, ok]) => !ok)
if (validatorFailed.length > 0) {
  console.error(
    `GATE FAIL: tensor-tree validator: ${validatorFailed.map(([name]) => name).join(', ')}`,
  )
  process.exit(1)
}

// structural parity of the JS encoder against the legacy fold
const legacyRoot = legacyTensorTree(moeTensors)
const index = createTensorTreeIndex(payload, moeTensors)
const parity = (() => {
  if (index === null) return { ok: false, reason: 'index rejected its own payload' }
  if (index.rootCount !== legacyRoot.totalCount) return { ok: false, reason: 'count' }
  if (index.rootParams !== legacyRoot.totalParams) return { ok: false, reason: 'params' }
  const legacyChildren = legacyRoot.children.map(c => c.segment).sort((a, b) => a.localeCompare(b))
  const indexChildren = index
    .childrenOf(0)
    .map(i => index.segmentOf(i))
    .sort((a, b) => a.localeCompare(b))
  if (JSON.stringify(legacyChildren) !== JSON.stringify(indexChildren))
    return { ok: false, reason: 'children' }
  const paramsOf = moeTensors.reduce((acc, t) => acc + tensorParams(t), 0)
  if (paramsOf !== legacyRoot.totalParams) return { ok: false, reason: 'params sum' }
  return { ok: true, nodes: index.size, count: index.rootCount, params: index.rootParams }
})()
if (!parity.ok) {
  console.error(`GATE FAIL: tensor-tree parity (${parity.reason})`)
  process.exit(1)
}

// ---------------------------------------------------------------------------
// optional: the Rust encoder must produce the SAME document as the JS fallback
// ---------------------------------------------------------------------------
let crossCheck = { ran: false, reason: 'not requested (pass --cross-check)' }
if (CROSS_CHECK) {
  crossCheck = runCrossCheck()
  if (crossCheck.ran && !crossCheck.identical) {
    console.error('GATE FAIL: the Rust tensor tree differs from the JS encoder')
    console.error(JSON.stringify(crossCheck.diff, null, 2).slice(0, 2000))
    process.exit(1)
  }
}

function runCrossCheck() {
  const fixtureDir = fs.mkdtempSync(path.join(os.tmpdir(), 'mmneo-tree-'))
  const namesPath = path.join(fixtureDir, 'names.json')
  // MoE-SHAPED names with tiny shapes: the tree only reads the header, so the
  // nesting/ordering/aggregates are fully exercised while the fixture stays a
  // few tens of kilobytes (a real 65k-tensor MoE would be gigabytes on disk).
  const subset = []
  for (let layer = 0; layer < 40; layer++) {
    for (const name of [
      'self_attn.q_proj.weight',
      'self_attn.k_proj.weight',
      'mlp.gate.weight',
      'input_layernorm.weight',
    ]) {
      subset.push({ name: `model.layers.${layer}.${name}`, dtype: 'BF16', shape: [2, 2] })
    }
    for (let expert = 0; expert < 16; expert++) {
      for (const proj of ['gate_proj', 'up_proj', 'down_proj']) {
        subset.push({
          name: `model.layers.${layer}.mlp.experts.${expert}.${proj}.weight`,
          dtype: 'BF16',
          shape: [2, 2],
        })
      }
    }
  }
  // the edge cases the grouping rule has to agree on
  subset.push(
    { name: 'scale', dtype: 'F32', shape: [] }, // scalar -> 1 parameter
    { name: 'a..b.w', dtype: 'F32', shape: [2] }, // empty level -> (unnamed)
    { name: 'noDots', dtype: 'F32', shape: [3] }, // root leaf
    { name: '.', dtype: 'F32', shape: [1] }, // two empty segments
    { name: 'deep.1.2.10.leaf', dtype: 'F32', shape: [4] },
    { name: '\u5c64.weight', dtype: 'F32', shape: [2] }, // non-ASCII segment
  )
  fs.writeFileSync(namesPath, JSON.stringify(subset.map(t => [t.name, t.dtype, t.shape])))
  const script = path.join(HERE, 'cross_check.py')
  const run = spawnSync(
    'python3',
    [
      script,
      '--names',
      namesPath,
      '--repo',
      REPO_ROOT,
      '--fixture',
      path.join(fixtureDir, 'tree.safetensors'),
    ],
    { encoding: 'utf8' },
  )
  if (run.status !== 0) {
    return {
      ran: false,
      reason: (run.stderr || run.stdout || 'python3 failed').trim().slice(0, 400),
    }
  }
  let rust
  try {
    rust = JSON.parse(run.stdout)
  } catch (e) {
    return { ran: false, reason: `unparsable python output: ${e.message}` }
  }
  if (rust.skipped) return { ran: false, reason: rust.skipped }
  const js = buildTensorTreePayload(subset)
  const identical = JSON.stringify(js) === JSON.stringify(rust.tree)
  return {
    ran: true,
    identical,
    tensors: subset.length,
    jsNodes: js.nodes.length,
    rustNodes: rust.tree.nodes.length,
    jsBytes: JSON.stringify(js).length,
    rustBytes: JSON.stringify(rust.tree).length,
    diff: identical ? null : { firstDifference: firstDifference(js, rust.tree) },
  }
}

const firstDifference = (a, b) => {
  const left = JSON.stringify(a)
  const right = JSON.stringify(b)
  for (let i = 0; i < Math.min(left.length, right.length); i++) {
    if (left[i] !== right[i]) {
      return {
        at: i,
        js: left.slice(Math.max(0, i - 60), i + 60),
        rust: right.slice(Math.max(0, i - 60), i + 60),
      }
    }
  }
  return { at: Math.min(left.length, right.length), js: left.slice(-80), rust: right.slice(-80) }
}

// ---------------------------------------------------------------------------
// gates + report
// ---------------------------------------------------------------------------
const ratio = (before, after) => before / after
const gates = {
  k15BudgetMs: 16,
  keystrokeP95Ms: grid.keystrokeHoisted.p95,
  keystrokeP95WithinBudget: grid.keystrokeHoisted.p95 <= 16,
  c1HoistingIsFaster: grid.keystrokeHoisted.p95 < grid.keystrokeNaive.p95,
  c1SpeedupP95: ratio(grid.keystrokeNaive.p95, grid.keystrokeHoisted.p95),
  // C2: the numeric variant must be served by the hoisted collator (32x on
  // V8) ...
  c2NumericHoistingIsFaster: grid.numericHoistedCollator.p50 < grid.numericLocaleCompare.p50,
  c2NumericSpeedupP50: ratio(grid.numericLocaleCompare.p50, grid.numericHoistedCollator.p50),
  // ... and the DEFAULT variant must stay on V8's localeCompare builtin, which
  // measures faster than a hoisted Intl.Collator (the gate pins that choice).
  c2DefaultComparatorIsTheFastestMeasured:
    grid.defaultLocaleCompare.p50 <= grid.defaultHoistedCollator.p50,
  c2DefaultLocaleCompareSpeedupP50: ratio(
    grid.defaultHoistedCollator.p50,
    grid.defaultLocaleCompare.p50,
  ),
  tensorTreeDecodeIsFasterThanTheBrowserFold:
    tree.indexCreate.p50 + tree.renderCollapsed.p50 < tree.legacyFold.p50,
  tensorTreeSpeedupP50: ratio(tree.legacyFold.p50, tree.indexCreate.p50 + tree.renderCollapsed.p50),
  rowsAreIdentical: sameRows,
  tensorTreeParity: parity.ok,
  tensorTreeValidatorRejectsBadPayloads: validatorFailed.length === 0,
  rustJsTreeIdentical: crossCheck.ran ? crossCheck.identical : null,
}
gates.passed =
  gates.c1HoistingIsFaster &&
  gates.c2NumericHoistingIsFaster &&
  gates.c2DefaultComparatorIsTheFastestMeasured &&
  gates.tensorTreeDecodeIsFasterThanTheBrowserFold &&
  gates.rowsAreIdentical &&
  gates.tensorTreeParity &&
  gates.tensorTreeValidatorRejectsBadPayloads &&
  gates.rustJsTreeIdentical !== false

const report = {
  phase: 6,
  kind: 'front',
  note:
    'Headless measurement of the REAL src/utils modules (compiled with the repository tsc). ' +
    'The "naive"/"legacy" sides are verbatim copies of the pre-Phase-6 component code, inlined ' +
    'here as the before-side of every gate. The gates are same-run ratios, so they hold on any ' +
    'machine; the absolute numbers belong to the env block below (K15 is judged on the reference ' +
    '8C/16T machine - Plan §2.2). The browser paint leg of K15 is instrumented in the app itself ' +
    '(src/utils/perf.ts: mm.grid.queryToPaint via __mmNeoPerf.summary()).',
  env: {
    date: new Date().toISOString().replace(/\.\d+Z$/, '+0000'),
    node: process.version,
    platform: `${os.type()}-${os.release()}-${os.arch()}`,
    cpus: os.cpus().length,
    cpu: os.cpus()[0]?.model?.trim() ?? 'unknown',
    memTotal: `${Math.round(os.totalmem() / 1024)} kB`,
    icu: process.config?.variables?.icu_small === undefined ? 'full-icu (default)' : 'system icu',
  },
  config: {
    models: models.length,
    keystrokes: QUERIES.length,
    columns: COLUMNS,
    moeTensors: moeTensors.length,
    moeLayers: MOE_LAYERS,
    moeExperts: MOE_EXPERTS,
  },
  grid,
  tensorTree: { ...tree, parity, crossCheck, validator: validatorCases },
  gates,
}

fs.mkdirSync(path.dirname(JSON_OUT), { recursive: true })
fs.writeFileSync(JSON_OUT, JSON.stringify(report, null, 2) + '\n')

const ms = v => `${v.toFixed(2)} ms`
console.log(`models: ${models.length}  keystrokes: ${QUERIES.length}  columns: ${COLUMNS}`)
console.log(
  `C1 filter+sort+chunk  naive p95 ${ms(grid.keystrokeNaive.p95)} -> hoisted ${ms(grid.keystrokeHoistedLocaleSort.p95)}`,
)
console.log(
  `C2 numeric segments   localeCompare(…, {numeric}) p50 ${ms(grid.numericLocaleCompare.p50)} -> hoisted collator ${ms(grid.numericHoistedCollator.p50)}`,
)
console.log(
  `C2 default segments   localeCompare p50 ${ms(grid.defaultLocaleCompare.p50)} vs hoisted collator ${ms(grid.defaultHoistedCollator.p50)} (builtin wins -> kept)`,
)
console.log(
  `K15 keystroke p95     ${ms(grid.keystrokeHoisted.p95)} (budget 16 ms; paint leg measured in-browser)`,
)
console.log(
  `K15 initial grid p95  naive ${ms(grid.initialRenderNaive.p95)} -> hoisted ${ms(grid.initialRenderHoisted.p95)}`,
)
console.log(
  `tensor tree (MoE ${moeTensors.length})  browser fold p50 ${ms(tree.legacyFold.p50)} -> rust payload decode p50 ${ms(tree.indexCreate.p50)} + render ${ms(tree.renderCollapsed.p50)}`,
)
console.log(
  `tensor tree payload   ${tree.payloadNodes} nodes, ${(tree.payloadBytes / 1e6).toFixed(2)} MB JSON`,
)
console.log(
  `tree validator      ${Object.keys(validatorCases).length} cases (accept/reject) as expected: ${
    validatorFailed.length === 0
  }`,
)
console.log(
  `cross-check (rust==js) ${crossCheck.ran ? crossCheck.identical : `skipped: ${crossCheck.reason}`}`,
)
console.log(`gates: ${gates.passed ? 'PASS' : 'FAIL'} -> ${JSON.stringify(gates, null, 0)}`)
console.log(`result: ${JSON_OUT}`)
fs.rmSync(OUT, { recursive: true, force: true })
process.exit(gates.passed ? 0 : 1)
