/**
 * The model-detail tensor tree (Plan §4.7.3 "テンソルツリー事前グループ化",
 * Phase 6).
 *
 * A large MoE header (~65k tensors) used to be folded into the display tree IN
 * THE BROWSER: 65k name splits, ~87k node objects, a Map of every dotted path
 * and an O(n log n) collation pass — measured ~0.73 s per open of the
 * Information tab (BENCH §11), all of it on the main thread.
 *
 * Two things remove that cost:
 *
 * 1. **Rust pre-grouping** — `mm_core.safetensors_tensor_tree` folds the tree
 *    during the header parse Neo already does and ships a compact PRE-ORDER
 *    table ([TensorTreePayload]); the leaf indices address the `tensors` array
 *    of the same response, so no tensor is transferred twice.
 * 2. **Lazy decoding** — [createTensorTreeIndex] turns that table into two
 *    typed arrays in one O(n) pass and then answers "children of node i" /
 *    "tensors of node i" WITHOUT ever materialising the 87k node objects: a
 *    collapsed tree renders ~2 nodes, an expanded one only its own subtree.
 *
 * The display order stays the historical one: the frontend applies
 * `naturalCompare` (utils/modelFilter) to the children / leaves it actually
 * renders, so the Rust fold (header order) and the JS fallback below are
 * indistinguishable on screen.
 *
 * [buildTensorTreePayload] is the fallback encoder for a backend that cannot
 * produce the tree (`MM_NATIVE=0`, a legacy engine, a non-safetensors model):
 * it reproduces the Rust grouping rule exactly, so the renderer has ONE code
 * path either way.
 */

import {
  type SafetensorsTensor,
  type TensorTreeNodeTuple,
  type TensorTreePayload,
} from 'types/typings'
import { naturalCompare } from 'utils/modelFilter'

/** Version of the wire format this decoder understands (the Rust encoder's
 *  `TENSOR_TREE_VERSION`). */
export const TENSOR_TREE_VERSION = 1

/** The name of an empty folder level (`a..b` → the middle level) — the same
 *  substitution the Rust fold and the historical frontend grouping apply. */
export const UNNAMED_SEGMENT = '(unnamed)'

// The wire types live in types/typings (BaseModel references them); re-exported
// here so consumers of this module have one import site.
export type { TensorTreeNodeTuple, TensorTreePayload }

/** One node as the renderer sees it. */
export interface TensorTreeNodeView {
  index: number
  segment: string
  /** Dotted path (the expansion-state key), `""` for the root. */
  path: string
  childCount: number
  tensorCount: number
  /** Subtree tensor count. */
  totalCount: number
  /** Subtree parameter count. */
  totalParams: number
}

/** Random access over a [TensorTreePayload] (no node objects materialised). */
export interface TensorTreeIndex {
  /** Number of node entries. */
  size: number
  /** Subtree tensor count of the root (= the tensor count). */
  rootCount: number
  /** Subtree parameter count of the root. */
  rootParams: number
  segmentOf(index: number): string
  /** `parentPath` + the node's own segment (the root's path is `""`). */
  pathOf(index: number, parentPath: string): string
  viewOf(index: number, parentPath: string): TensorTreeNodeView
  /** Child node indices, in the display order (`naturalCompare` on segment). */
  childrenOf(index: number): number[]
  /** The node's own tensors, in the display order (`naturalCompare` on the
   *  name tail below `path`). */
  tensorsOf(index: number, path: string): SafetensorsTensor[]
}

/** `shape.reduce((acc, dim) => acc * dim, 1)` — a scalar counts as 1. */
export const tensorParams = (tensor: Pick<SafetensorsTensor, 'shape'>): number =>
  (tensor.shape ?? []).reduce((acc, dim) => acc * dim, 1)

/** The leaf label of a tensor inside a node (its name minus the node path). */
export const tensorTail = (path: string, tensor: SafetensorsTensor): string =>
  path ? (tensor.name ?? '').slice(path.length + 1) : (tensor.name ?? '')

interface BuildNode {
  segment: string
  children: number[]
  leaves: number[]
  /** Subtree tensor count (own + descendants). */
  count: number
  /** Subtree parameter count. */
  params: number
}

/**
 * Fold a tensor list into the wire format — the JS mirror of the Rust encoder
 * (same grouping rule, same pre-order, own leaves before children, header
 * order within a node). Used when the backend sent no tree.
 */
export const buildTensorTreePayload = (tensors: SafetensorsTensor[]): TensorTreePayload => {
  const nodes: BuildNode[] = [{ segment: '', children: [], leaves: [], count: 0, params: 0 }]
  /** `parents[i]` < i always (a folder is created by the tensor that first
   *  mentions it), which is what makes the aggregate pass a reverse scan. */
  const parents: number[] = [-1]
  const byPath = new Map<string, number>()

  tensors.forEach((tensor, index) => {
    const segments = (tensor.name ?? '').split('.')
    let parent = 0
    let path = ''
    for (let i = 0; i < segments.length - 1; i++) {
      const segment = segments[i] || UNNAMED_SEGMENT
      path = path ? `${path}.${segment}` : segment
      let node = byPath.get(path)
      if (node === undefined) {
        node = nodes.length
        nodes.push({ segment, children: [], leaves: [], count: 0, params: 0 })
        parents.push(parent)
        nodes[parent].children.push(node)
        byPath.set(path, node)
      }
      parent = node
    }
    const target = nodes[parent]
    target.leaves.push(index)
    target.count += 1
    target.params += tensorParams(tensor)
  })

  // Bottom-up aggregates: a parent always has a SMALLER index than its child
  // (it is created while walking the path of the tensor that mentions it), so
  // one reverse pass folds every subtree into its parent.
  for (let i = nodes.length - 1; i > 0; i--) {
    const child = nodes[i]
    const ancestor = nodes[parents[i]]
    ancestor.count += child.count
    ancestor.params += child.params
  }

  // Pre-order emit (own leaves before children), iteratively: a pathologically
  // deep name must not overflow the JS stack either.
  const outNodes: TensorTreeNodeTuple[] = []
  const outLeaves: number[] = []
  const stack: [number, number][] = [[0, 0]]
  while (stack.length > 0) {
    const frame = stack[stack.length - 1]
    const [index, next] = frame
    const node = nodes[index]
    if (next === 0) {
      outNodes.push([
        node.segment,
        node.children.length,
        node.leaves.length,
        node.count,
        node.params,
      ])
      for (const leaf of node.leaves) outLeaves.push(leaf)
    }
    if (next < node.children.length) {
      frame[1] = next + 1
      stack.push([node.children[next], 0])
    } else {
      stack.pop()
    }
  }
  return { v: TENSOR_TREE_VERSION, nodes: outNodes, leaves: outLeaves }
}

/**
 * Validate a payload and build the random-access index over it.
 *
 * Returns `null` when the document cannot be trusted (wrong version, a shape
 * that does not walk, a leaf index outside the tensor list) — the caller then
 * falls back to [buildTensorTreePayload], so a hostile or stale tree can never
 * render a wrong table.
 */
export const createTensorTreeIndex = (
  payload: unknown,
  tensors: SafetensorsTensor[],
): TensorTreeIndex | null => {
  if (!payload || typeof payload !== 'object') return null
  const candidate = payload as Partial<TensorTreePayload>
  if (candidate.v !== TENSOR_TREE_VERSION) return null
  if (!Array.isArray(candidate.nodes) || !Array.isArray(candidate.leaves)) return null
  const nodes = candidate.nodes
  const leaves = candidate.leaves
  if (nodes.length === 0) return null
  for (const node of nodes) {
    if (!Array.isArray(node) || node.length !== 5) return null
    if (typeof node[0] !== 'string') return null
    for (const field of [node[1], node[2], node[3], node[4]]) {
      if (typeof field !== 'number' || !Number.isFinite(field) || field < 0) return null
    }
  }
  for (const leaf of leaves) {
    if (typeof leaf !== 'number' || !Number.isInteger(leaf) || leaf < 0 || leaf >= tensors.length) {
      return null
    }
  }

  const size = nodes.length
  // Leaf offset of each node: own-leaves-first emission means the offsets are
  // the running sum of `tensorCount` in table order.
  const leafOffset = new Int32Array(size)
  let cursor = 0
  let ownTotal = 0
  for (let i = 0; i < size; i++) {
    leafOffset[i] = cursor
    const count = nodes[i][2]
    cursor += count
    ownTotal += count
  }
  if (cursor !== leaves.length || ownTotal !== leaves.length) return null

  // Subtree size (in node entries) of each node, for O(1) sibling skips:
  // a parent always precedes its children, so a reverse pass over the parent
  // links folds the sizes up.
  const subtree = new Int32Array(size).fill(1)
  const parent = new Int32Array(size).fill(-1)
  const stack: number[] = []
  const remaining = new Int32Array(size)
  for (let i = 0; i < size; i++) {
    while (stack.length > 0 && remaining[stack[stack.length - 1]] === 0) stack.pop()
    if (stack.length === 0 && i !== 0) return null // a second root: not pre-order
    parent[i] = stack.length > 0 ? stack[stack.length - 1] : -1
    if (parent[i] >= 0) remaining[parent[i]] -= 1
    stack.push(i)
    remaining[i] = nodes[i][1]
  }
  if (stack.some(index => remaining[index] !== 0)) return null // unfinished frames
  for (let i = size - 1; i > 0; i--) subtree[parent[i]] += subtree[i]
  if (subtree[0] !== size) return null

  const segmentOf = (index: number): string => nodes[index][0]

  const childrenOf = (index: number): number[] => {
    const childCount = nodes[index][1]
    const children: number[] = []
    let at = index + 1
    for (let i = 0; i < childCount; i++) {
      children.push(at)
      at += subtree[at]
    }
    children.sort((a, b) => naturalCompare(segmentOf(a), segmentOf(b)))
    return children
  }

  const tensorsOf = (index: number, path: string): SafetensorsTensor[] => {
    const count = nodes[index][2]
    const start = leafOffset[index]
    const out: SafetensorsTensor[] = []
    for (let i = start; i < start + count; i++) {
      const tensor = tensors[leaves[i]]
      if (tensor) out.push(tensor)
    }
    out.sort((a, b) => naturalCompare(tensorTail(path, a), tensorTail(path, b)))
    return out
  }

  const pathOf = (index: number, parentPath: string): string => {
    if (index === 0) return ''
    const segment = segmentOf(index)
    return parentPath ? `${parentPath}.${segment}` : segment
  }

  return {
    size,
    rootCount: nodes[0][3],
    rootParams: nodes[0][4],
    segmentOf,
    pathOf,
    viewOf: (index, parentPath) => ({
      index,
      segment: segmentOf(index),
      path: pathOf(index, parentPath),
      childCount: nodes[index][1],
      tensorCount: nodes[index][2],
      totalCount: nodes[index][3],
      totalParams: nodes[index][4],
    }),
    childrenOf,
    tensorsOf,
  }
}
