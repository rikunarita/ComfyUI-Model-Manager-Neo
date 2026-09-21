/**
 * Media file utility functions
 */

/**
 * The default preview artwork (glass NO-PREVIEW.svg). Models and download
 * tasks without a preview reference this URL directly - it is a default,
 * not a fallback: the preview routes no longer substitute anything.
 */
export const NO_PREVIEW_URL = '/model-manager/no-preview.svg'

/**
 * Value the backend puts in `preview` when a model (or a download task) has no
 * preview file on disk. It is a sentinel, not a path: `py/utils.py` names the
 * same constant `NO_PREVIEW_SENTINEL`, and both sides swap it for
 * NO_PREVIEW_URL before it ever reaches an `<img src>`.
 */
export const NO_PREVIEW_SENTINEL = 'no-preview.png'

/**
 * Base path of the browser-cacheable SVG artwork served by the backend
 * (`GET /model-manager/assets/<name>.svg`, ETag + max-age). The icons used to
 * be inlined as data: URIs, so every folder card carried its own copy and the
 * browser could never cache any of it (optimization B-2).
 */
const ASSET_BASE = '/model-manager/assets'

export const assetUrl = (name: string) => `${ASSET_BASE}/${name}.svg`

/**
 * Model-hub logos (`assets/AIModelHub-Logos/`), worn as the background of the
 * "open model page" button whenever the model's notes record which platform
 * it came from (the `website` key of the front-matter, surfaced by the scan
 * as `modelPlatform`).
 */
const PLATFORM_LOGO: Record<string, string> = {
  civitai: assetUrl('civitai-icon'),
  huggingface: assetUrl('hf-icon'),
  modelscope: assetUrl('modelscope-icon'),
}

/**
 * Folded spelling (`www.` stripped, case / spaces / separators removed) →
 * logo key. The notes keep the human-readable platform name — the resolver
 * writes `Hugging Face` (two words), which a single-word lookup missed, so
 * Hugging Face models showed no logo — and hand-written front-matter may use
 * the short or domain form (`hf`, `huggingface.co`, `www.modelscope.ai`,
 * `civitai.red`). Every spelling of a hub resolves to the same logo.
 */
const PLATFORM_ALIASES: Record<string, string> = {
  civitai: 'civitai',
  civitaicom: 'civitai',
  civitaired: 'civitai',
  hf: 'huggingface',
  huggingface: 'huggingface',
  huggingfaceco: 'huggingface',
  modelscope: 'modelscope',
  modelscopeai: 'modelscope',
  modelscopecn: 'modelscope',
}

const normalizePlatform = (platform: string): string | undefined => {
  const folded = platform
    .trim()
    .toLowerCase()
    .replace(/^www\./, '')
    .replace(/[\s_.\-]+/g, '')
  return PLATFORM_ALIASES[folded]
}

/** The logo URL of a model platform, if Neo ships one for it. */
export const platformLogo = (platform: string | undefined): string | undefined => {
  if (!platform) return undefined
  const key = normalizePlatform(platform)
  return key ? PLATFORM_LOGO[key] : undefined
}

/**
 * Background style putting the platform logo behind the "open model page"
 * button. A translucent dark layer keeps the white link glyph readable on
 * both logos; without a known platform the button keeps its plain chrome.
 */
export const platformBackgroundStyle = (platform: string | undefined) => {
  const logo = platformLogo(platform)
  if (!logo) return undefined
  return {
    backgroundImage: `linear-gradient(rgb(0 0 0 / 0.35), rgb(0 0 0 / 0.35)), url(${logo})`,
    backgroundSize: 'cover',
    backgroundPosition: 'center',
  }
}

/**
 * Tag local preview URLs with the save-time bust token: a primary-preview
 * swap rewrites the bytes behind unchanged URLs, so without the tag the
 * browser keeps painting the already-decoded old image.
 */
export const withPreviewBust = (url: string, bust: number): string => {
  if (!url || !bust) return url
  if (!url.startsWith('/model-manager/preview/')) return url
  return `${url}${url.includes('?') ? '&' : '?'}pb=${bust}`
}

const VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.m4v', '.ogv']

const VIDEO_HOST_PATTERNS = [
  '/video', // Civitai video URLs often end with /video
  'type=video', // URLs with video type parameter
  'format=video', // URLs with video format parameter
  'video.civitai.com', // Civitai video domain
]

/**
 * Detect if a URL points to a video based on extension or URL patterns
 * @param url - The URL to check
 * @param localContentType - Optional MIME type for local files
 */
export const isVideoUrl = (url: string, localContentType?: string): boolean => {
  if (!url) return false

  // For local files with known MIME type
  if (localContentType && localContentType.startsWith('video/')) {
    return true
  }

  const urlLower = url.toLowerCase()

  // First check if URL ends with a video extension
  for (const ext of VIDEO_EXTENSIONS) {
    if (urlLower.endsWith(ext)) {
      return true
    }
  }

  // Check if URL contains a video extension anywhere (for complex URLs like Civitai)
  if (VIDEO_EXTENSIONS.some(ext => urlLower.includes(ext))) {
    return true
  }

  // Check for specific video hosting patterns
  return VIDEO_HOST_PATTERNS.some(pattern => urlLower.includes(pattern))
}
