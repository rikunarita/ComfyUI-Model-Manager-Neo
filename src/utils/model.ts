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
export const isZnnFolderName = (name: string) => name.endsWith('_ZNN')

/** True for ZipNN bundle / delta folders (`X_DeltaZNN`). */
export const isDeltaFolderName = (name: string) => name.endsWith('_DeltaZNN')

/**
 * True for ANY ZipNN bundle folder: batch bundles (`X_DeltaZNN`, legacy
 * `X_ZNN`) and delta folders (`<base>_DeltaZNN`). Every bundle shows the
 * inverted ZipNN button and batch-decompresses back to its source folder.
 */
export const isBundleFolderName = (name: string) => isZnnFolderName(name) || isDeltaFolderName(name)
