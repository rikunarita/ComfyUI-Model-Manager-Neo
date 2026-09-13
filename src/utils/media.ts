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
export const ASSET_BASE = '/model-manager/assets'

export const assetUrl = (name: string) => `${ASSET_BASE}/${name}.svg`

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
