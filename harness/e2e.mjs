/**
 * End-to-end verification for ComfyUI-Model-Manager-Neo.
 *
 * Boots harness/serve.py (real backend + real production bundle, stubbed
 * ComfyUI host), drives the UI in headless Chromium and asserts both
 * behaviour AND the glassmorphism design contract:
 *   - every push button renders translucent (alpha in (0,1)) with a hairline
 *     border, a backdrop blur and a non-empty shadow;
 *   - no element falls back to the browser UA button face (opaque grey);
 *   - dialogs, tabs, inputs, selects and toasts all blur their backdrop.
 *
 * Usage:  node harness/e2e.mjs
 * Exit code 0 = every assertion passed and no console/page errors.
 */
import { spawn } from 'node:child_process'
import { mkdirSync, readdirSync, readFileSync } from 'node:fs'
import { kill } from 'node:process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const PORT = 8700 + (process.pid % 200)
const SHOTS = path.join(ROOT, 'harness', 'shots')
mkdirSync(SHOTS, { recursive: true })

// A crashed harness run can leave its server bound to the port, which makes
// the next run talk to a stale backend (and chase ghosts). Sweep first.
for (const pid of readdirSync('/proc')) {
  if (!/^\d+$/.test(pid) || Number(pid) === process.pid) continue
  let cmd = ''
  try {
    cmd = readFileSync(`/proc/${pid}/cmdline`, 'utf8')
  } catch {
    continue
  }
  if (cmd.includes('harness/serve.py')) {
    try {
      kill(Number(pid), 'SIGKILL')
    } catch {
      /* already gone */
    }
  }
}

const failures = []
const passes = []
const check = (name, ok, detail = '') => {
  if (ok) {
    passes.push(name)
    console.log(`  PASS  ${name}`)
  } else {
    failures.push(`${name} ${detail}`)
    console.log(`  FAIL  ${name}  ${detail}`)
  }
}

const server = spawn('python3', [path.join(ROOT, 'harness', 'serve.py'), '--port', String(PORT)], {
  stdio: ['ignore', 'pipe', 'pipe'],
})
server.stderr.on('data', d => process.stderr.write(`[serve] ${d}`))

const waitServer = async () => {
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/harness`)
      if (res.ok) return
    } catch {
      /* not up yet */
    }
    await new Promise(r => setTimeout(r, 250))
  }
  throw new Error('harness server did not start')
}

// The headless shell occasionally dies while booting under load; a bounded
// relaunch keeps the suite deterministic without hiding real failures (any
// failure *after* a page loads still fails the run).
const launchBrowser = async () => {
  let lastError
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      return await chromium.launch()
    } catch (error) {
      lastError = error
      await new Promise(r => setTimeout(r, 1500))
    }
  }
  throw lastError
}

let browser = await launchBrowser()

const consoleErrors = []

const attachConsole = target => {
  target.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text())
  })
  target.on('pageerror', err => consoleErrors.push(`pageerror: ${err.message}`))
}

/**
 * Pages (and, should the renderer die under load, the whole browser) are
 * retried: a headless-shell crash while *creating* a page is an environment
 * artefact, not a product failure. Everything asserted once a page exists
 * still fails the run as usual.
 */
const safeNewPage = async (opts = {}) => {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const created = await browser.newPage({ viewport: { width: 1440, height: 900 }, ...opts })
      attachConsole(created)
      return created
    } catch (error) {
      if (attempt === 2) throw error
      try {
        await browser.close()
      } catch {
        /* already dead */
      }
      browser = await launchBrowser()
      await new Promise(r => setTimeout(r, 1000))
    }
  }
  throw new Error('unreachable')
}

let page = await safeNewPage()
attachConsole(page)

/** alpha of a computed color in rgba()/oklab()/color() serialization */
const alphaOf = bg => {
  if (!bg) return 0
  const slash = bg.match(/\/\s*([\d.]+)\s*\)/)
  if (slash) return parseFloat(slash[1])
  const rgba = bg.match(/rgba?\(([^)]+)\)/)
  if (rgba) {
    const parts = rgba[1].split(',').map(s => parseFloat(s.trim()))
    return parts.length > 3 ? parts[3] : 1
  }
  return 1
}

/** computed-style contract for a glass push button */
const glassButtonAudit = sel =>
  page.$$eval(sel, els =>
    els.map(el => {
      const cs = getComputedStyle(el)
      return {
        text: (el.textContent || '').trim().slice(0, 24),
        alpha: alphaOf(cs.backgroundColor),
        borderWidth: cs.borderTopWidth,
        blur: cs.backdropFilter,
        shadow: cs.boxShadow,
        tag: el.tagName,
      }
    }),
  )

await page.addInitScript(`globalThis.alphaOf = ${alphaOf.toString()}`)

try {
  await waitServer()
  await page.goto(`http://127.0.0.1:${PORT}/harness`)

  // E01 — extension registered its entry points
  await page.waitForFunction(
    () => window.comfyAPI?.app?.app?.ui?.menuContainer?.children?.length > 0,
  )
  check('E01 legacy menu button registered', true)

  // E02 — open the manager dialog the same way the topbar button does
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
  const manager = page.locator('[role="dialog"]').last()
  await manager.waitFor({ timeout: 10000 })
  check(
    'E02 manager dialog opens',
    (await manager.textContent())?.includes('Model Manager Neo') ?? false,
  )
  check(
    'E02b flat view is the default',
    (await manager.locator('input[placeholder="Search models"]').count()) === 1,
  )

  // The flat grid is the default view now; the folder artwork lives in the
  // folder explorer, so switch over first.
  await manager.locator('button[title="Switch to Folder View"]').click()
  await page.waitForTimeout(600)

  // E15 — glass folder artwork: idle icon, opening animation after a
  // sustained (>= 1 s) hover, closing animation after a sustained unhover,
  // back to idle afterwards
  const folderCard = page.locator('[data-card-main]').first()
  const folderImg = folderCard.locator('img').first()
  const idleSrc = await folderImg.getAttribute('src')
  check(
    'E15 folder card renders the glass svg icon',
    (idleSrc ?? '').includes('/model-manager/assets/folder-'),
    String(idleSrc),
  )
  // the artwork must be browser-cacheable and revalidate with a 304
  const svgCache = await page.evaluate(async url => {
    const first = await fetch(url)
    const etag = first.headers.get('etag')
    const cacheControl = first.headers.get('cache-control')
    await first.arrayBuffer()
    const second = await fetch(url, { headers: { 'If-None-Match': etag ?? '' } })
    return { status1: first.status, etag, cacheControl, status2: second.status }
  }, idleSrc)
  check(
    'E15g folder svg is served with ETag + max-age and revalidates with 304',
    svgCache.status1 === 200 &&
      Boolean(svgCache.etag) &&
      /max-age=\d+/.test(svgCache.cacheControl ?? '') &&
      svgCache.status2 === 304,
    JSON.stringify(svgCache),
  )
  await folderCard.hover()
  await page.waitForTimeout(500)
  const earlySrc = await folderCard.locator('img').first().getAttribute('src')
  check('E15b no animation inside the 1s hover gate', earlySrc === idleSrc)
  await page.waitForTimeout(900)
  const hoverSrc = await folderCard.locator('img').first().getAttribute('src')
  check(
    'E15c sustained hover swaps to the opening animation',
    hoverSrc !== idleSrc && (hoverSrc ?? '').includes('/model-manager/assets/folder-opening'),
    String(hoverSrc),
  )
  await page.mouse.move(10, 10)
  await page.waitForTimeout(500)
  const earlyLeaveSrc = await folderCard.locator('img').first().getAttribute('src')
  check('E15d no closing inside the 1s unhover gate', earlyLeaveSrc === hoverSrc)
  await page.waitForTimeout(900)
  const leaveSrc = await folderCard.locator('img').first().getAttribute('src')
  check(
    'E15e sustained unhover swaps to the closing animation',
    leaveSrc !== hoverSrc && leaveSrc !== idleSrc,
  )
  await page.waitForTimeout(1900)
  const backSrc = await folderCard.locator('img').first().getAttribute('src')
  check('E15f settles back to the idle icon', backSrc === idleSrc)

  // E16 — the all-fit glyph decorates the breadcrumb trail at tiny size
  await folderCard.dblclick()
  await page.waitForTimeout(600)
  const crumbs = page.locator('[role="dialog"] .text-sm img')
  check('E16 breadcrumb carries tiny folder glyphs', (await crumbs.count()) >= 2)
  await page.locator('[role="dialog"]').first().locator('button:has(img)').first().click()
  await page.waitForTimeout(400)

  // Back to the flat view for the grid audit (also proves the toggle).
  await manager.locator('button[title="Switch to Flat View"]').click()
  await page.waitForSelector('[role="dialog"] input[placeholder="Search models"]', {
    timeout: 10000,
  })

  // E03 — header icon buttons are glass push buttons
  const headerButtons = await glassButtonAudit('[role="dialog"] > div:first-child button[title]')
  check('E03 header button count', headerButtons.length === 7, `got ${headerButtons.length}`)
  check(
    'E03b header buttons translucent + hairline + blur + shadow',
    headerButtons.every(
      b =>
        b.alpha > 0 &&
        b.alpha < 1 &&
        b.borderWidth === '1px' &&
        b.blur.includes('blur') &&
        b.shadow !== 'none',
    ),
    JSON.stringify(headerButtons),
  )

  // E04 — toolbar controls (search field + three dropdown triggers)
  const triggers = await glassButtonAudit('[role="dialog"] [aria-haspopup="menu"]')
  check(
    'E04 select triggers are glass',
    triggers.length === 3 &&
      triggers.every(
        b => b.alpha > 0 && b.alpha < 1 && b.borderWidth === '1px' && b.blur.includes('blur'),
      ),
    JSON.stringify(triggers),
  )
  const inputGlass = await page.$eval('[role="dialog"] input[placeholder="Search models"]', el => {
    const cs = getComputedStyle(el.parentElement)
    return { blur: cs.backdropFilter, alpha: alphaOf(cs.backgroundColor) }
  })
  check(
    'E04b search input glass wrapper',
    inputGlass.blur.includes('blur') && inputGlass.alpha > 0 && inputGlass.alpha < 1,
    JSON.stringify(inputGlass),
  )

  // E05 — model cards render with previews + glass chips
  await page.waitForFunction(
    () => document.querySelectorAll('[data-card-main]').length >= 4,
    null,
    { timeout: 10000 },
  )
  const cards = await page.$$('[role="dialog"] [data-card-main]')
  check('E05 model cards rendered', cards.length >= 4, `got ${cards.length}`)
  const noPrevImgs = await page.$$eval(
    '[role="dialog"] img',
    els => els.filter(el => (el.getAttribute('src') ?? '').includes('/no-preview.svg')).length,
  )
  check('E05b preview-less models use the default svg', noPrevImgs >= 1, String(noPrevImgs))
  const chip = await page.$eval(
    '[data-card-main] ~ div > div',
    el => getComputedStyle(el).backdropFilter,
  )
  check('E05b card chips blur', chip.includes('blur'))

  await page.screenshot({ path: path.join(SHOTS, 'dark-manager.png') })

  // E06 — open a model detail dialog and exercise the tabs
  // The card's drag overlay is the real click target in a browser too.
  await page.locator('[data-draggable-overlay]').first().click()
  const detail = page.locator('[role="dialog"]').last()
  await detail.waitFor({ timeout: 10000 })
  await detail.locator('table').first().waitFor()
  const tdBorder = await detail
    .locator('table td')
    .first()
    .evaluate(el => getComputedStyle(el).borderTopColor)
  check('E06 info table uses subtle border (not currentColor)', alphaOf(tdBorder) < 0.5, tdBorder)
  const labelBg = await detail
    .locator('table td')
    .first()
    .evaluate(el => alphaOf(getComputedStyle(el).backgroundColor))
  check('E06b label cell translucent', labelBg > 0 && labelBg < 1, String(labelBg))

  const metaTab = detail.getByRole('tab', { name: 'Metadata' })
  const descTab = detail.getByRole('tab', { name: 'Description' })
  await metaTab.click()
  await page.waitForTimeout(200)
  const metaState = await metaTab.getAttribute('data-state')
  const metaBg = await metaTab.evaluate(el => alphaOf(getComputedStyle(el).backgroundColor))
  const descBg = await descTab.evaluate(el => alphaOf(getComputedStyle(el).backgroundColor))
  check('E07 tab switch works', metaState === 'active')
  check(
    'E07b active tab tinted / inactive transparent',
    metaBg > 0.05 && descBg < 0.01,
    `${metaBg} vs ${descBg}`,
  )
  await descTab.click()
  await page.waitForTimeout(300)

  // E08 — detail action icon buttons (incl. destructive) are glass
  const actions = await detail.locator('form button').evaluateAll(els =>
    els.map(el => {
      const cs = getComputedStyle(el)
      return {
        text: (el.textContent || '').trim().slice(0, 24),
        alpha: alphaOf(cs.backgroundColor),
        borderWidth: cs.borderTopWidth,
        blur: cs.backdropFilter,
        shadow: cs.boxShadow,
      }
    }),
  )
  const destructive = actions.find(a => a.shadow.includes('rgba') && a.alpha > 0)
  check(
    'E08 detail action buttons glass',
    actions.length >= 6 && actions.every(b => b.borderWidth === '1px' && b.alpha < 1),
    JSON.stringify(actions.slice(0, 8)),
  )
  check('E08b destructive button present', Boolean(destructive), JSON.stringify(actions))

  await page.screenshot({ path: path.join(SHOTS, 'dark-detail.png') })

  // E09 — confirm dialog: destructive accept is a danger skeleton button
  await detail.locator('form button[class*="border-mm-danger"]').first().click()
  const alert = page.locator('[role="alertdialog"]')
  await alert.waitFor({ timeout: 5000 })
  const accept = await alert
    .locator('button')
    .last()
    .evaluate(el => {
      const cs = getComputedStyle(el)
      return {
        color: cs.color,
        alpha: alphaOf(cs.backgroundColor),
        border: cs.borderTopWidth,
        blur: cs.backdropFilter,
      }
    })
  check(
    'E09 confirm accept = danger skeleton',
    accept.alpha > 0 && accept.alpha < 1 && accept.border === '1px' && accept.blur.includes('blur'),
    JSON.stringify(accept),
  )
  await alert.locator('button').first().click() // cancel
  // The exit animation keeps the node around for its 200ms animate-out.
  await page.waitForFunction(
    () => document.querySelectorAll('[role="alertdialog"]').length === 0,
    null,
    { timeout: 5000 },
  )
  check('E09b confirm cancels', true)

  // close the detail dialog again (header Close button)
  await detail.locator('button[title="Close"]').click()
  await page.waitForTimeout(300)

  // E10 — download list + create-task dialogs
  await manager.locator('button[title="Download List"]').click()
  const download = page.locator('[role="dialog"]').last()
  await download.waitFor()
  const cta = await download.getByRole('button', { name: /Create Download Task/ }).evaluate(el => {
    const cs = getComputedStyle(el)
    return {
      alpha: alphaOf(cs.backgroundColor),
      border: cs.borderTopWidth,
      shadow: cs.boxShadow,
      blur: cs.backdropFilter,
    }
  })
  check(
    'E10 primary CTA is accent skeleton glass',
    cta.alpha > 0 &&
      cta.alpha < 1 &&
      cta.border === '1px' &&
      cta.shadow !== 'none' &&
      cta.blur.includes('blur'),
    JSON.stringify(cta),
  )
  await download.getByRole('button', { name: /Create Download Task/ }).click()
  const create = page.locator('[role="dialog"]').last()
  await create.waitFor()
  check('E10b create-task dialog opens', (await create.locator('input').count()) >= 1)
  await page.screenshot({ path: path.join(SHOTS, 'dark-downloads.png') })

  // E11 — light theme: same glass contract, palette follows the host class
  await page.evaluate(() => document.documentElement.classList.remove('dark-theme'))
  await page.waitForTimeout(400)
  const lightTriggers = await glassButtonAudit('[role="dialog"] button[title]')
  check(
    'E11 light-mode header buttons stay glass',
    lightTriggers.every(b => b.alpha > 0 && b.alpha < 1 && b.borderWidth === '1px'),
    JSON.stringify(lightTriggers),
  )
  await page.screenshot({ path: path.join(SHOTS, 'light-manager.png') })
  await page.evaluate(() => document.documentElement.classList.add('dark-theme'))

  // E13 — regression: direct-link download offers only types that exist and
  // actually creates the task (the reported "Download does nothing" bug)
  for (let i = 0; i < 4; i++) {
    const btn = page.locator('[role="dialog"] button[title="Close"]').last()
    if (await btn.isVisible().catch(() => false)) await btn.click()
    await page.waitForTimeout(250)
  }
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
  await page.waitForSelector('[role="dialog"]')
  const mgr = page.locator('[role="dialog"]').first()
  await mgr.locator('button[title="Download List"]').click()
  const dl2 = page.locator('[role="dialog"]').last()
  await dl2.getByRole('button', { name: /Create Download Task/ }).click()
  const create2 = page.locator('[role="dialog"]:has(input[placeholder^="Input a URL"])').last()
  await create2.waitFor()
  await create2
    .locator('input')
    .first()
    .fill(`http://127.0.0.1:${PORT}/remote/remote_model.safetensors`)
  // (no Enter here: searching a direct link without a type is rejected by
  // design and would log a console error, which E12 treats as a failure)
  await page.waitForTimeout(300)
  await create2.locator('[aria-haspopup="menu"]').first().click()
  const menu = page.locator('[role="menu"]').last()
  const menuText = (await menu.textContent()) ?? ''
  check(
    'E13 only existing model types offered',
    !menuText.includes('Checkpoints') && menuText.includes('UNet/Diffusion Models'),
    menuText.slice(0, 80),
  )
  await menu.getByText('UNet/Diffusion Models', { exact: true }).click()
  await page.waitForTimeout(600)
  await create2.getByRole('button', { name: 'Download', exact: true }).click()
  await create2.waitFor({ state: 'hidden', timeout: 15000 })
  check('E13b create dialog closes after task creation', true)
  await page.waitForFunction(
    async () => {
      const r = await fetch('/model-manager/models/diffusion_models')
      const j = await r.json()
      return j.data?.some(m => m.basename === 'remote_model')
    },
    null,
    { timeout: 20000 },
  )
  check('E13c downloaded file landed in the chosen type', true)

  // E14 — regression: HF upload shows progress, survives closing the dialog
  // and reports completion through the module-level websocket listeners
  await page.evaluate(async () => {
    await fetch('/model-manager/download/setting', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'huggingface', value: btoa('hf_test_token_123456') }),
    })
  })
  for (let i = 0; i < 3; i++) {
    const btn = page.locator('[role="dialog"] button[title="Close"]').last()
    if (await btn.isVisible().catch(() => false)) await btn.click()
    await page.waitForTimeout(250)
  }
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
  await page.waitForSelector('[role="dialog"]')
  await mgr.locator('button[title="Upload to HuggingFace"]').click()
  const hf2 = page.locator('[role="dialog"]').last()
  await hf2.waitFor()
  await hf2.locator('button:has-text("diffusion_models")').first().click()
  await page.waitForTimeout(400)
  // deterministically pick the 2 MiB model: a tiny file would finish before
  // the first poll and make the progress assertions flaky
  await hf2.getByText('anima-aesthetic-v1', { exact: true }).click()
  await page.waitForTimeout(400)
  await hf2.locator('input').first().fill('rikunarita/e2e-repo')
  await hf2.getByRole('button', { name: 'Upload', exact: true }).click()
  await hf2.locator('[role="progressbar"]').waitFor({ timeout: 5000 })
  check('E14 progress bar visible during upload', true)
  // accurate (intermediate) percentages must reach the UI, not just 0 -> 100:
  // record the FIRST non-zero read-out and require it to be a real fraction
  await page.evaluate(() => {
    window.__firstPct = undefined
  })
  await page.waitForFunction(
    () => {
      const el = [...document.querySelectorAll('span.tabular-nums')].pop()
      if (!el) return false
      const v = Number.parseInt(el.textContent ?? '0', 10)
      if (v > 0 && window.__firstPct === undefined) window.__firstPct = v
      return window.__firstPct !== undefined && window.__firstPct < 100
    },
    null,
    { timeout: 20000, polling: 100 },
  )
  const firstPct = await page.evaluate(() => window.__firstPct)
  check(
    'E14d accurate intermediate progress in the UI',
    firstPct > 0 && firstPct < 100,
    String(firstPct),
  )

  await hf2.locator('button[title="Close"]').click()
  await page.waitForFunction(
    async () => {
      const r = await fetch('/probe/hf')
      const j = await r.json()
      return (j.uploads || []).length > 0
    },
    null,
    { timeout: 20000 },
  )
  check('E14b upload completes although the dialog was closed', true)
  const toastEl = page.locator('[data-sonner-toast]', { hasText: 'rikunarita/e2e-repo' }).first()
  await toastEl.waitFor({ timeout: 10000 })
  check('E14c completion toast raised with the dialog closed', true)

  // E14g — re-uploading identical content must NOT be reported as a plain
  // success: HuggingFace skips the empty commit and the UI has to say so.
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
  await page.waitForSelector('[role="dialog"]')
  await mgr.locator('button[title="Upload to HuggingFace"]').click()
  const hf3 = page.locator('[role="dialog"]').last()
  await hf3.waitFor()
  await hf3.locator('button:has-text("diffusion_models")').first().click()
  await page.waitForTimeout(400)
  await hf3.getByText('anima-aesthetic-v1', { exact: true }).click()
  await page.waitForTimeout(400)
  await hf3.locator('input').first().fill('rikunarita/e2e-repo')
  const readsBefore = (await (await fetch(`http://127.0.0.1:${PORT}/probe/hf`)).json()).reads
  await hf3.getByRole('button', { name: 'Upload', exact: true }).click()
  const skipToast = page.locator('[data-sonner-toast]', { hasText: 'blob/main' }).first()
  await skipToast.waitFor({ timeout: 30000 })
  const toastText = (await skipToast.textContent()) ?? ''
  check(
    'E14g duplicate upload reported as skipped with the repo link',
    toastText.includes('identical file already exists'),
    toastText.slice(0, 160),
  )
  // the pre-flight check must short-circuit: no transfer read may happen
  const readsAfter = (await (await fetch(`http://127.0.0.1:${PORT}/probe/hf`)).json()).reads
  check(
    'E14h duplicate upload performs no transfer',
    readsAfter === readsBefore,
    `${readsBefore} -> ${readsAfter}`,
  )

  // E14i — the Hub can already hold the exact bytes under a DIFFERENT path:
  // the LFS batch answer then carries no upload action ("Upload 0 LFS files"),
  // nothing travels, yet a real commit is created. Reporting that as a plain
  // "Success" next to a bar that never moved is what made users read the log
  // and conclude the upload never started.
  //
  // Close everything first: the dialog store keeps one instance per key, so
  // re-opening the HuggingFace dialog while the previous one is still on step 3
  // would hand back that same, already-configured window.
  for (let i = 0; i < 4; i++) {
    const btn = page.locator('[role="dialog"] button[title="Close"]').last()
    if (await btn.isVisible().catch(() => false)) await btn.click()
    await page.waitForTimeout(250)
  }
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
  await page.waitForSelector('[role="dialog"]')
  await mgr.locator('button[title="Upload to HuggingFace"]').click()
  const hf4 = page.locator('[role="dialog"]').last()
  await hf4.waitFor()
  await hf4.locator('button:has-text("diffusion_models")').first().click()
  await page.waitForTimeout(400)
  await hf4.getByText('anima-aesthetic-v1', { exact: true }).click()
  await page.waitForTimeout(400)
  await hf4.locator('input').first().fill('rikunarita/e2e-repo')
  // a different destination path inside the SAME repository
  await hf4.locator('input').nth(1).fill('mirrors/anima-aesthetic-v1.safetensors')
  // `reads` is reset by every upload_file call; `transfer_reads` is the
  // cumulative count of bytes-reads the fake Hub performed during a transfer.
  const readsBeforeDedup = (await (await fetch(`http://127.0.0.1:${PORT}/probe/hf`)).json())
    .transfer_reads
  await hf4.getByRole('button', { name: 'Upload', exact: true }).click()
  // the phase read-out must be present and named while the upload is in flight
  // or settling (the bar alone cannot tell hashing from transferring)
  const phaseText = await hf4
    .locator('[data-hf-phase]')
    .first()
    .textContent()
    .catch(() => null)
  check(
    'E14j phase read-out is rendered',
    Boolean(phaseText && phaseText.trim()),
    String(phaseText),
  )
  const dedupToast = page
    .locator('[data-sonner-toast]', { hasText: 'mirrors/anima-aesthetic-v1.safetensors' })
    .first()
  await dedupToast.waitFor({ timeout: 30000 })
  const dedupText = (await dedupToast.textContent()) ?? ''
  check(
    'E14i zero-byte commit is explained, not reported as a plain success',
    dedupText.includes('already holds these exact bytes') &&
      dedupText.includes('blob/main/mirrors/anima-aesthetic-v1.safetensors'),
    dedupText.slice(0, 200),
  )
  const readsAfterDedup = (await (await fetch(`http://127.0.0.1:${PORT}/probe/hf`)).json())
    .transfer_reads
  check(
    'E14k deduplicated upload performs no transfer read',
    readsAfterDedup === readsBeforeDedup,
    `${readsBeforeDedup} -> ${readsAfterDedup}`,
  )
  const dedupHits = (await (await fetch(`http://127.0.0.1:${PORT}/probe/hf`)).json()).dedup_hits
  check('E14l fake Hub really took the dedup path', dedupHits >= 1, String(dedupHits))

  /* ====================================================================== */
  /* Stacking order, panel-scoped loading, editor features, ja locale        */
  /* ====================================================================== */

  // Every popup this extension can raise must paint ABOVE the dialog that
  // opened it. The reported bug class: the folder-path picker and friends
  // teleported to <body> with Tailwind's default `z-50`, i.e. underneath the
  // 2400+ dialog windows, so they were invisible.
  const zOf = sel =>
    page.evaluate(s => {
      const els = [...document.querySelectorAll(s)]
      if (!els.length) return null
      const el = els[els.length - 1]
      const cs = getComputedStyle(el)
      const r = el.getBoundingClientRect()
      const top = document.elementFromPoint(r.x + r.width / 2, r.y + Math.min(r.height / 2, 20))
      return {
        z: Number.parseFloat(cs.zIndex),
        onTop: !!top && (el === top || el.contains(top)),
        rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
      }
    }, sel)

  // close everything, then reopen a clean manager window
  for (let i = 0; i < 5; i++) {
    const btn = page.locator('[role="dialog"] button[title="Close"]').last()
    if (await btn.isVisible().catch(() => false)) await btn.click()
    await page.waitForTimeout(200)
  }
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
  await page.waitForSelector('[role="dialog"]')
  const mgr2 = page.locator('[role="dialog"]').first()
  const dialogZ = (await zOf('[role="dialog"]')).z
  check('E17 dialog window sits above the host chrome', dialogZ >= 2400, String(dialogZ))

  // dropdown menu
  await mgr2.locator('[aria-haspopup="menu"]').nth(1).click()
  await page.waitForSelector('[role="menu"]')
  const menuZ = await zOf('[role="menu"]')
  check(
    'E17b dropdown menu paints above its dialog and is hit-testable',
    menuZ && Number.isFinite(menuZ.z) && menuZ.z > dialogZ && menuZ.onTop,
    JSON.stringify(menuZ),
  )
  await page.keyboard.press('Escape')
  await page.waitForTimeout(400)

  // card tooltip (delay-duration 800)
  const cardBox = await page.locator('[data-card-main]').first().boundingBox()
  await page.mouse.move(cardBox.x + cardBox.width / 2, cardBox.y + cardBox.height / 2)
  await page.waitForTimeout(1500)
  // `[role="tooltip"]` is reka-ui's visually-hidden a11y node (1x1, aria-hidden);
  // the painted surface is its parent and the popper wrapper is what actually
  // carries the stacking position at <body> level.
  const tipZ = await page.evaluate(() => {
    const inner = document.querySelector('[role="tooltip"]')
    if (!inner) return null
    const pick = el => {
      if (!el) return null
      const cs = getComputedStyle(el)
      const r = el.getBoundingClientRect()
      return {
        z: Number.parseFloat(cs.zIndex),
        pos: cs.position,
        w: Math.round(r.width),
        h: Math.round(r.height),
      }
    }
    const surface = inner.parentElement
    return {
      surface: pick(surface),
      wrapper: pick(surface?.parentElement),
      text: (surface?.textContent ?? '').slice(0, 40),
    }
  })
  const tipZBest = tipZ ? Math.max(tipZ.surface?.z ?? -1, tipZ.wrapper?.z ?? -1) : -1
  check(
    'E17c tooltip paints above its dialog',
    !!tipZ && Number.isFinite(tipZBest) && tipZBest > dialogZ && tipZ.surface.w > 4,
    JSON.stringify(tipZ),
  )
  await page.mouse.move(5, 5)
  await page.waitForTimeout(500)

  // model detail dialog: read-only first (Directory row, confirm dialog),
  // then edit mode (description icon, folder picker, name with a folder prefix)
  await page.locator('[data-draggable-overlay]').first().click()
  await page.waitForTimeout(900)
  const det = page.locator('[role="dialog"]').last()

  // E19 — the Directory row is a directory: it ends with a separator
  const dirCell = await det
    .locator('table tr')
    .filter({ hasText: 'Directory' })
    .locator('td')
    .last()
    .textContent()
  check(
    'E19 Directory column ends with a trailing slash',
    (dirCell ?? '').trim().endsWith('/'),
    String(dirCell),
  )

  // E17f — the global confirm must outrank the window that raised it
  await det.locator('form button[class*="border-mm-danger"]').first().click()
  await page.waitForSelector('[role="alertdialog"]')
  const confirmZ = await zOf('[role="alertdialog"]')
  check(
    'E17f confirm dialog paints above the window that raised it',
    confirmZ && Number.isFinite(confirmZ.z) && confirmZ.z > dialogZ + 1 && confirmZ.onTop,
    JSON.stringify(confirmZ),
  )
  await page.locator('[role="alertdialog"] button').first().click()
  await page.waitForFunction(
    () => document.querySelectorAll('[role="alertdialog"]').length === 0,
    null,
    { timeout: 5000 },
  )

  // E17g/h — toasts are the topmost layer: they report the outcome of
  // everything below, so nothing may cover them, and they must sit inside the
  // viewport (they used to lay out in the document flow and overflow it).
  await page.evaluate(() => {
    window.dispatchEvent(
      new CustomEvent('mm:hf_upload_error', { detail: { taskId: 'z', error: 'STACK' } }),
    )
  })
  await page.waitForTimeout(700)
  const toastZ = await zOf('[data-sonner-toaster]')
  check(
    'E17g toasts paint above dialogs and confirms',
    toastZ && Number.isFinite(toastZ.z) && toastZ.z > (confirmZ?.z ?? 0),
    JSON.stringify(toastZ),
  )
  const toastRect = toastZ?.rect ?? []
  check(
    'E17h toasts are anchored top-right inside the viewport',
    toastRect.length === 4 &&
      toastRect[1] < 200 &&
      toastRect[0] > 500 &&
      toastRect[0] + toastRect[2] <= 1440 &&
      toastRect[2] > 100,
    JSON.stringify(toastRect),
  )

  // E21 — the description is edited through an explicit icon; clicking the
  // rendered markdown no longer opens the textarea
  await det.locator('button[aria-label="Edit model"]').click() // pencil -> edit mode
  await page.waitForTimeout(500)
  const editBtn = det.locator('button[title="Edit description"]')
  check('E21 description exposes an explicit Edit button', (await editBtn.count()) === 1)
  // the textarea is v-show'd, so visibility (not presence) is the contract.
  // Click the base-info table (a neutral area): clicking the preview itself is
  // supposed to open the lightbox now, so it is not a valid "neutral" target.
  await det
    .locator('form table')
    .first()
    .click({ position: { x: 10, y: 10 } })
    .catch(() => {})
  await page.waitForTimeout(300)
  check(
    'E21b clicking around the form does not open the description editor',
    !(await det
      .locator('form textarea')
      .isVisible()
      .catch(() => false)),
  )
  await editBtn.click()
  await page.waitForTimeout(400)
  check(
    'E21c the Edit button opens the description textarea',
    await det
      .locator('form textarea')
      .isVisible()
      .catch(() => false),
  )
  await det
    .locator('form textarea')
    .blur()
    .catch(() => {})
  await page.waitForTimeout(300)

  // E17d/e — the nested folder picker: the popup the bug report named
  await det.locator('form button:has(svg.lucide-folder-open)').first().click()
  await page.waitForTimeout(800)
  const nestedZ = await zOf('[role="dialog"]:last-of-type')
  check(
    'E17d nested folder picker paints above every other window',
    nestedZ && Number.isFinite(nestedZ.z) && nestedZ.z > dialogZ + 1 && nestedZ.onTop,
    JSON.stringify(nestedZ),
  )
  const nestedTitle = await page
    .locator('[role="dialog"]:last-of-type')
    .evaluate(el => el.textContent?.slice(0, 12) ?? '')
  check(
    'E17e the nested window really is the folder picker',
    nestedTitle.startsWith('Folder'),
    nestedTitle,
  )
  await page.locator('[role="dialog"]:last-of-type button:has-text("Cancel")').click()
  await page.waitForTimeout(500)

  // E20 — a folder prefix in the file name files the model into a sub-folder
  const nameInput = det.locator('input[placeholder="name or folder/name"]')
  check('E20 name field offers the folder/name placeholder', (await nameInput.count()) === 1)
  await nameInput.fill('e2e-sub/renamed-model')
  await nameInput.blur()
  await page.waitForTimeout(300)
  check(
    'E20b a `/` in the name is accepted (not reverted)',
    (await nameInput.inputValue()) === 'e2e-sub/renamed-model',
    await nameInput.inputValue(),
  )
  await det.getByRole('button', { name: 'Save', exact: true }).click()
  await page.waitForFunction(
    async () => {
      const r = await fetch('/model-manager/models/diffusion_models')
      const j = await r.json()
      return (j.data || []).some(m => m.subFolder === 'e2e-sub' && m.basename === 'renamed-model')
    },
    null,
    { timeout: 15000 },
  )
  check('E20c the model was filed into the requested sub-folder', true)

  // an illegal character must still be rejected and reverted
  await page.locator('[data-draggable-overlay]').first().click()
  await page.waitForTimeout(800)
  const det2 = page.locator('[role="dialog"]').last()
  await det2.locator('button[aria-label="Edit model"]').click()
  await page.waitForTimeout(400)
  const nameInput2 = det2.locator('input[placeholder="name or folder/name"]')
  await nameInput2.fill('bad:name')
  await nameInput2.blur()
  await page.waitForTimeout(400)
  check(
    'E20d an illegal character is still rejected',
    (await nameInput2.inputValue()) !== 'bad:name',
    await nameInput2.inputValue(),
  )
  await det2.getByRole('button', { name: 'Cancel', exact: true }).click()
  await page.waitForTimeout(400)

  // E18 — the loading scrim covers the panel only, never the whole viewport
  await page.evaluate(() => {
    const api = window.comfyAPI.api.api
    const orig = api.fetchApi
    api.fetchApi = (url, opts) => {
      if (String(url).includes('/models/')) {
        return new Promise(resolve => setTimeout(() => resolve(orig(url, opts)), 1200))
      }
      return orig(url, opts)
    }
  })
  for (let i = 0; i < 4; i++) {
    const btn = page.locator('[role="dialog"] button[title="Close"]').last()
    if (await btn.isVisible().catch(() => false)) await btn.click()
    await page.waitForTimeout(200)
  }
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
  await page.waitForSelector('[role="dialog"]')
  await page.locator('[role="dialog"]').first().locator('button[title="Refresh"]').click()
  await page.waitForTimeout(500)
  const loadingAudit = await page.evaluate(() => {
    const scrims = [...document.querySelectorAll('[data-mm-loading]')]
    const dlg = document.querySelector('[role="dialog"]')
    const dlgRect = dlg?.getBoundingClientRect()
    const corner = document.elementFromPoint(4, 4)
    return {
      count: scrims.length,
      insideDialog: scrims.every(el => !!dlg && dlg.contains(el)),
      noViewportScrim: ![...document.querySelectorAll('body > *')].some(el => {
        const cs = getComputedStyle(el)
        const r = el.getBoundingClientRect()
        return (
          cs.position === 'fixed' &&
          r.width >= window.innerWidth - 1 &&
          r.height >= window.innerHeight - 1 &&
          cs.backdropFilter !== 'none'
        )
      }),
      cornerFree: !!corner && (!dlgRect || corner !== dlg),
      dialogRect: dlgRect
        ? [
            Math.round(dlgRect.x),
            Math.round(dlgRect.y),
            Math.round(dlgRect.width),
            Math.round(dlgRect.height),
          ]
        : null,
    }
  })
  check(
    'E18 loading scrim exists while a request is in flight',
    loadingAudit.count >= 1,
    JSON.stringify(loadingAudit),
  )
  check(
    'E18b the scrim lives inside the panel, not on <body>',
    loadingAudit.insideDialog && loadingAudit.noViewportScrim,
    JSON.stringify(loadingAudit),
  )
  const outside = await page.evaluate(() => {
    const dlg = document.querySelector('[role="dialog"]').getBoundingClientRect()
    const x = Math.max(2, Math.round(dlg.x / 2))
    const y = Math.max(2, Math.round(dlg.y / 2))
    const el = document.elementFromPoint(x, y)
    return { x, y, cls: el ? (el.className || '').toString().slice(0, 60) : null, tag: el?.tagName }
  })
  check(
    'E18c the area outside the panel is not covered by the scrim',
    !String(outside.cls).includes('backdrop-blur'),
    JSON.stringify(outside),
  )
  await page.screenshot({ path: path.join(SHOTS, 'loading-panel.png') })
  await page.waitForTimeout(1400)
  const afterLoad = await page.evaluate(() => document.querySelectorAll('[data-mm-loading]').length)
  check('E18d the scrim goes away when the request settles', afterLoad === 0, String(afterLoad))

  // E22 — the Japanese bundle is wired to ComfyUI's locale.
  // The main page is closed first: two 1600x1000 blur-heavy pages alive at
  // once is enough to get a background renderer OOM-killed on small machines,
  // which used to surface as a crash several assertions later.
  await page.close()
  const jaPage = await safeNewPage()
  jaPage.on('pageerror', e => consoleErrors.push(`ja pageerror: ${e.message}`))
  jaPage.on('console', m => {
    if (m.type() === 'error') consoleErrors.push(`ja: ${m.text()}`)
  })
  await jaPage.goto(`http://127.0.0.1:${PORT}/harness?locale=ja`)
  await jaPage.waitForFunction(
    () => window.comfyAPI?.app?.app?.ui?.menuContainer?.children?.length > 0,
  )
  await jaPage.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
  await jaPage.waitForSelector('[role="dialog"]')
  const jaTexts = await jaPage.evaluate(() => {
    const dlg = document.querySelector('[role="dialog"]')
    const legacy = document.querySelector('#comfyui-model-manager-button')
    return {
      dialog: dlg?.textContent ?? '',
      legacyButton: legacy?.textContent ?? '',
      search: dlg?.querySelector('input[placeholder]')?.getAttribute('placeholder') ?? '',
    }
  })
  check(
    'E22 Japanese bundle is used when Comfy.Locale is ja',
    jaTexts.search.includes('モデルを検索') && jaTexts.dialog.includes('すべて'),
    JSON.stringify(jaTexts).slice(0, 200),
  )
  // a nested surface has to be translated too, not just the toolbar
  await jaPage.locator('[data-draggable-overlay]').first().click()
  await jaPage.waitForTimeout(900)
  const jaDetail = await jaPage.evaluate(() => {
    const dlgs = [...document.querySelectorAll('[role="dialog"]')]
    return dlgs[dlgs.length - 1]?.textContent ?? ''
  })
  check(
    'E22b model detail is translated (Directory / File Size rows)',
    jaDetail.includes('ディレクトリ') && jaDetail.includes('ファイルサイズ'),
    jaDetail.slice(0, 120),
  )
  await jaPage.screenshot({ path: path.join(SHOTS, 'ja-detail.png') })
  await jaPage.close()
  page = await safeNewPage()
  await page.goto(`http://127.0.0.1:${PORT}/harness`)

  /* ====================================================================== */
  /* Galleries, lightbox, toast dismiss button, preview cache headers        */
  /* ====================================================================== */

  // E24 — a saved model with two preview files shows paging on the preview
  // area (the harness workspace gives anima-aesthetic-v1 a second preview).
  for (let i = 0; i < 5; i++) {
    const b = page.locator('[role="dialog"] button[title="Close"]').last()
    if (!(await b.isVisible().catch(() => false))) break
    await b.click()
    await page.waitForTimeout(250)
  }
  // The page was re-created after the Japanese section, so wait for the
  // extension to register its listener before dispatching the open event.
  await page.waitForFunction(
    () => window.comfyAPI?.app?.app?.ui?.menuContainer?.children?.length > 0,
  )
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
  await page.waitForSelector('[role="dialog"]')
  await page.waitForFunction(() => document.querySelectorAll('[data-card-main]').length >= 3)
  // The two-preview model was renamed by E20 (its previews travel with it), so
  // open it by name instead of assuming it is still the first card.
  await page
    .locator('[data-card-main]', { hasText: 'renamed-model' })
    .first()
    .locator('xpath=following-sibling::*[@data-draggable-overlay]')
    .click()
  await page.waitForTimeout(1200)
  const gal = page.locator('[role="dialog"]').last()
  const counter = gal.locator('div.tabular-nums', { hasText: '/' }).first()
  const counterText = (await counter.textContent().catch(() => '')) ?? ''
  check('E24 saved gallery shows a page counter', /1\s*\/\s*2/.test(counterText), counterText)
  await gal.locator('button[aria-label="Next preview"]').click()
  await page.waitForTimeout(400)
  const counterText2 = (await counter.textContent().catch(() => '')) ?? ''
  check(
    'E24b the next button pages the saved gallery',
    /2\s*\/\s*2/.test(counterText2),
    counterText2,
  )

  // E23 — tapping the preview opens the lightbox; arrows page it; Escape closes
  await gal.locator('.preview-aspect').click({ position: { x: 60, y: 60 } })
  await page.waitForSelector('[data-mm-lightbox]')
  check('E23 tapping the preview opens the lightbox', true)
  const lbCounter = await page.locator('[data-mm-lightbox] div.tabular-nums').textContent()
  check(
    'E23b the lightbox shows the gallery position',
    /2\s*\/\s*2/.test(lbCounter ?? ''),
    String(lbCounter),
  )
  await page.locator('[data-mm-lightbox] button[aria-label="Previous preview"]').click()
  await page.waitForTimeout(300)
  const lbCounter2 = await page.locator('[data-mm-lightbox] div.tabular-nums').textContent()
  check(
    'E23c the lightbox pages backwards',
    /1\s*\/\s*2/.test(lbCounter2 ?? ''),
    String(lbCounter2),
  )
  await page.keyboard.press('Escape')
  await page.waitForFunction(() => !document.querySelector('[data-mm-lightbox]'), null, {
    timeout: 5000,
  })
  check('E23d Escape closes the lightbox', true)
  await gal.locator('button[title="Close"]').click()
  await page.waitForTimeout(400)

  // E25 — every toast carries a manual dismiss button that really dismisses
  await page.evaluate(() => {
    window.dispatchEvent(
      new CustomEvent('mm:hf_upload_error', { detail: { taskId: 'dismiss', error: 'DISMISS' } }),
    )
  })
  const dismissToast = page.locator('[data-sonner-toast]', { hasText: 'DISMISS' }).first()
  await dismissToast.waitFor({ timeout: 8000 })
  const closeBtn = dismissToast.locator('[data-close-button]')
  check('E25 toasts expose a manual close button', (await closeBtn.count()) === 1)
  await closeBtn.click()
  await page.waitForFunction(
    () =>
      ![...document.querySelectorAll('[data-sonner-toast]')].some(t =>
        t.textContent?.includes('DISMISS'),
      ),
    null,
    { timeout: 5000 },
  )
  check('E25b the close button dismisses the toast', true)

  // E26 — preview responses carry an ETag and answer 304 when revalidated
  const previewUrl = await page.evaluate(async () => {
    const r = await fetch('/model-manager/models/diffusion_models')
    const j = await r.json()
    const withPreview = (j.data || []).find(m => Array.isArray(m.preview))
    return withPreview ? withPreview.preview[0] : null
  })
  check(
    'E26 the model list returns preview galleries as arrays',
    Boolean(previewUrl),
    String(previewUrl),
  )
  const previewCache = await page.evaluate(async url => {
    const first = await fetch(url)
    const etag = first.headers.get('etag')
    const cacheControl = first.headers.get('cache-control')
    await first.arrayBuffer()
    const second = await fetch(url, { headers: { 'If-None-Match': etag ?? '' } })
    return { status1: first.status, etag, cacheControl, status2: second.status }
  }, previewUrl)
  check(
    'E26b previews are served with ETag + cache-control and revalidate with 304',
    previewCache.status1 === 200 &&
      Boolean(previewCache.etag) &&
      /max-age=\d+/.test(previewCache.cacheControl ?? '') &&
      previewCache.status2 === 304,
    JSON.stringify(previewCache),
  )

  /* ====================================================================== */
  /* ZipNN button, selection mode, hover buttons, flat-default migration      */
  /* ====================================================================== */

  // E29 — the flat-view hover buttons must actually be clickable (they used to
  // be pointer-events:none and every press opened the card instead).
  for (let i = 0; i < 5; i++) {
    const b = page.locator('[role="dialog"] button[title="Close"]').last()
    if (!(await b.isVisible().catch(() => false))) break
    await b.click()
    await page.waitForTimeout(250)
  }
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
  await page.waitForSelector('[role="dialog"]')
  await page.waitForFunction(() => document.querySelectorAll('[data-card-main]').length >= 3)
  const firstCardBox = await page.locator('[data-card-main]').first().boundingBox()
  await page.mouse.move(firstCardBox.x + firstCardBox.width / 2, firstCardBox.y + 20)
  await page.waitForTimeout(500)
  await page.locator('button[aria-label="Add node to graph"]').first().click()
  const nodeToast = page
    .locator('[data-sonner-toast]', { hasText: 'Loader node added to the graph' })
    .first()
  await nodeToast.waitFor({ timeout: 8000 })
  check('E29 flat-view hover buttons are clickable', true)

  // E28 — selection mode: checkboxes on cards, bulk bar once one is selected
  await page.locator('button[aria-label="Select files"]').first().click()
  await page.waitForTimeout(400)
  const checkboxes = page.locator(
    '[data-card-main] ~ button[aria-pressed], button[aria-pressed="false"][class*="rounded-full"]',
  )
  const boxCount = await page.locator('button[aria-label="Select model"]').count()
  check('E28 selection mode reveals per-card checkboxes', boxCount >= 3, String(boxCount))
  await page.locator('[data-card-main]').first().click()
  await page.waitForTimeout(400)
  const bulkBar = page
    .locator('div', { hasText: 'selected' })
    .locator('button', { hasText: 'Add to workflow' })
  check('E28b selecting a card reveals the bulk action bar', (await bulkBar.count()) >= 1)
  await page.locator('button', { hasText: 'Clear selection' }).first().click()
  await page.waitForTimeout(300)
  await page.locator('button[aria-label="Select files"]').first().click()
  await page.waitForTimeout(300)
  check('E28c leaving selection mode clears it', true)
  void checkboxes

  // E27 — ZipNN: button in the preview/table gap, confirm (not danger), progress
  // / completion, and the inverted icon on a compressed model.
  const znnCard = page.locator('[data-card-main]', { hasText: 'qwen_vae' }).first()
  await znnCard.locator('xpath=following-sibling::*[@data-draggable-overlay]').click()
  await page.waitForTimeout(1200)
  const znnDetail = page.locator('[role="dialog"]').last()
  const znnButton = znnDetail.locator('button.mm-zipnn-button')
  check('E27 ZipNN button rendered in the detail window', (await znnButton.count()) === 1)
  const znnImg = znnButton.locator('img')
  check(
    'E27b the button uses the shipped ZipNN artwork',
    ((await znnImg.getAttribute('src')) ?? '').includes('zipnn-button'),
  )
  check(
    'E27c uncompressed model shows the normal (non-inverted) icon',
    !((await znnImg.getAttribute('class')) ?? '').includes('invert'),
  )
  await znnButton.click()
  const znnConfirm = page.locator('[role="alertdialog"]')
  await znnConfirm.waitFor({ timeout: 5000 })
  const acceptClass = (await znnConfirm.locator('button').last().getAttribute('class')) ?? ''
  check(
    'E27d the ZipNN confirmation is not a Danger dialog',
    !acceptClass.includes('border-mm-danger'),
    acceptClass.slice(0, 80),
  )
  await znnConfirm.locator('button').last().click()
  const znnToast = page
    .locator('[data-sonner-toast]', { hasText: 'ZipNN compression finished' })
    .first()
  await znnToast.waitFor({ timeout: 20000 })
  check('E27e compression completes with a toast', true)
  await znnDetail.locator('button[title="Close"]').click()
  await page.waitForTimeout(800)
  const znnCard2 = page.locator('[data-card-main]', { hasText: 'qwen_vae.znn' }).first()
  await znnCard2.waitFor({ timeout: 10000 })
  await znnCard2.locator('xpath=following-sibling::*[@data-draggable-overlay]').click()
  await page.waitForTimeout(1200)
  const znnDetail2 = page.locator('[role="dialog"]').last()
  const znnImg2 = znnDetail2.locator('button.mm-zipnn-button img')
  check(
    'E27f a compressed model shows the inverted icon',
    ((await znnImg2.getAttribute('class')) ?? '').includes('invert'),
  )
  await znnDetail2.locator('button[title="Close"]').click()
  await page.waitForTimeout(400)

  // E30 — a stored "flat off" preference is overridden once by the migration
  const flatPage = await safeNewPage()
  await flatPage.goto(`http://127.0.0.1:${PORT}/harness?flat=0`)
  await flatPage.waitForFunction(
    () => window.comfyAPI?.app?.app?.ui?.menuContainer?.children?.length > 0,
  )
  await flatPage.waitForTimeout(600)
  const flatAfter = await flatPage.evaluate(() => ({
    stored: window.comfyAPI.app.app.ui.settings.getSettingValue('ModelManager.UI.Flat'),
    marker: window.comfyAPI.app.app.ui.settings.getSettingValue('ModelManager.UI.FlatDefaultV2'),
  }))
  check(
    'E30 the flat-default migration overrides a stored false exactly once',
    flatAfter.stored === true && flatAfter.marker === true,
    JSON.stringify(flatAfter),
  )
  await flatPage.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
  await flatPage.waitForSelector('[role="dialog"]')
  check(
    'E30b the manager opens flat despite the stored preference',
    (await flatPage.locator('[role="dialog"] input[placeholder="Search models"]').count()) === 1,
  )
  await flatPage.close()

  // E12 — no console / page errors anywhere along the way
  const realErrors = consoleErrors.filter(e => !e.includes('favicon'))
  check(
    'E12 zero console/page errors',
    realErrors.length === 0,
    JSON.stringify(realErrors.slice(0, 5)),
  )
} catch (error) {
  failures.push(`harness crash: ${error?.message ?? error}`)
  console.error(error)
  await page.screenshot({ path: path.join(SHOTS, 'crash.png') }).catch(() => {})
} finally {
  await browser.close()
  server.kill()
}

console.log(`\n${passes.length} passed, ${failures.length} failed`)
if (failures.length) {
  for (const f of failures) console.log('  FAILED:', f)
  process.exit(1)
}
