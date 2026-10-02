import { type BaseModel } from 'types/typings'

const loader = {
  checkpoints: 'CheckpointLoaderSimple',
  loras: 'LoraLoader',
  vae: 'VAELoader',
  clip: 'CLIPLoader',
  diffusion_models: 'UNETLoader',
  unet: 'UNETLoader',
  clip_vision: 'CLIPVisionLoader',
  style_models: 'StyleModelLoader',
  embeddings: undefined,
  diffusers: 'DiffusersLoader',
  vae_approx: undefined,
  controlnet: 'ControlNetLoader',
  gligen: 'GLIGENLoader',
  upscale_models: 'UpscaleModelLoader',
  hypernetworks: 'HypernetworkLoader',
  photomaker: 'PhotoMakerLoader',
  classifiers: undefined,
}

export const resolveModelTypeLoader = (type: string) => {
  return (loader as Record<string, string | undefined>)[type]
}

export const genModelKey = (model: BaseModel) => {
  return `${model.type}:${model.pathIndex}:${model.subFolder}:${model.basename}${model.extension}`
}

/**
 * True for legacy ZipNN bundle folders (`X_ZNN`, created by older versions).
 * Mirrors `py/utils.py`: `X_DeltaZNN` does NOT match (the char before "ZNN"
 * is a letter), so the two suffixes stay distinguishable.
 */
const isZnnFolderName = (name: string) => name.endsWith('_ZNN')

/** True for ZipNN bundle / delta folders (`X_DeltaZNN`). */
const isDeltaFolderName = (name: string) => name.endsWith('_DeltaZNN')

/**
 * True for ANY ZipNN bundle folder: batch bundles (`X_DeltaZNN`, legacy
 * `X_ZNN`) and delta folders (`<base>_DeltaZNN`). Every bundle shows the
 * inverted ZipNN button and batch-decompresses back to its source folder.
 */
const isBundleFolderName = (name: string) => isZnnFolderName(name) || isDeltaFolderName(name)

/**
 * Minimal tree-node shape `folderBatchDirection` walks (structural typing
 * keeps this utility free of hook imports).
 */
/**
 * The batch direction a folder's CONTENT implies - the frontend mirror of the
 * backend `mode: "auto"` resolution (py/compress.py): any plain
 * `.safetensors` anywhere in the sub-tree means compress; otherwise any ZipNN
 * content (bundle folders, in-place `.znn.safetensors`, delta `.znn`) means
 * decompress; a folder without ZipNN-relevant content yields 'empty'.
 *
 * Bundle-named folders short-circuit to 'decompress' (their content is ZipNN
 * by definition), which also keeps folder cards correct when a render path
 * hands over a node without `children`. This is what makes a type root that
 * keeps its bundle inside itself (`T/T_DeltaZNN`) show the inverted,
 * decompress-styled button once only bundles remain.
 */
export const folderBatchDirection = (
  // Structural tree-node shape (basename/extension/isFolder/children), kept
  // inline so the exported signature leaks no private type (fallow gate).
  node: { basename: string; extension?: string; isFolder?: boolean; children?: readonly unknown[] },
): 'compress' | 'decompress' | 'empty' => {
  if (isBundleFolderName(node.basename)) return 'decompress'
  let plain = false
  let znn = false
  type Node = typeof node
  const walk = (current: Node): void => {
    for (const child of (current.children ?? []) as readonly Node[]) {
      if (child.isFolder) {
        if (isBundleFolderName(child.basename)) znn = true
        walk(child)
      } else if (child.extension === '.safetensors') {
        if (child.basename.endsWith('.znn')) znn = true
        else plain = true
      } else if (child.extension === '.znn') {
        znn = true
      }
    }
  }
  walk(node)
  return plain ? 'compress' : znn ? 'decompress' : 'empty'
}
