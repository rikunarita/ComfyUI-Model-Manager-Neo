/**
 * Screenshot / screen-recording capture for `docs/screenshots/`.
 *
 * Boots harness/serve.py (the REAL Python routes + the REAL production bundle
 * from web/) and drives it in headless Chromium at 1600x1000, dark theme,
 * exactly like harness/e2e.mjs does — so every picture in the documentation is
 * a genuine render of the shipped code, not a mock-up.
 *
 * The host chrome is the harness's stand-in gradient (ComfyUI itself is not
 * running), and the model names come from the harness workspace; capture from a
 * live ComfyUI window if you want your own library in the shot. See
 * docs/screenshots/README.md for the per-file manifest.
 *
 * Usage:  pnpm capture            (PNGs)
 *         pnpm capture --video    (also records docs/screenshots/hero.webm)
 *
 * Requires ffmpeg on PATH for the GIF variants (hero.gif, node-graph.gif);
 * without it the webm recordings are still written and the conversion command
 * is printed.
 */
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const OUT = path.join(ROOT, 'docs', 'screenshots')
const PORT = 8900 + (process.pid % 90)
const WITH_VIDEO = process.argv.includes('--video')
mkdirSync(OUT, { recursive: true })

// A crashed run can leave its server bound to the port, which makes the next
// run talk to a stale backend. Sweep first (same guard as harness/e2e.mjs).
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
      process.kill(Number(pid), 'SIGKILL')
    } catch {
      /* already gone */
    }
  }
}

const server = spawn('python3', [path.join(ROOT, 'harness', 'serve.py'), '--port', String(PORT)], {
  stdio: ['ignore', 'pipe', 'pipe'],
})
server.stderr.on('data', d => process.stderr.write(`[serve] ${d}`))

const waitServer = async () => {
  for (let i = 0; i < 80; i++) {
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

const written = []
const save = name => {
  written.push(name)
  console.log(`  wrote docs/screenshots/${name}`)
}

await waitServer()
const browser = await chromium.launch()

const newPage = async (opts = {}) => {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, ...opts })
  page.on('pageerror', e => console.error('PAGEERROR', e.message))
  return page
}

const openManager = async page => {
  await page.goto(`http://127.0.0.1:${PORT}/harness`)
  await page.waitForFunction(
    () => window.comfyAPI?.app?.app?.ui?.menuContainer?.children?.length > 0,
  )
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
  await page.waitForSelector('[role="dialog"]')
  await page.waitForFunction(() => document.querySelectorAll('[data-card-main]').length >= 3)
  return page.locator('[role="dialog"]').first()
}

/** Close every window, then re-open the manager so a section starts clean. */
const ensureManager = async page => {
  // A nested (modal) dialog paints an overlay that swallows clicks on the
  // windows below it, so dismiss it through its own Cancel button first.
  for (let i = 0; i < 3; i++) {
    const cancel = page.locator('[role="dialog"]:last-of-type button:has-text("Cancel")').last()
    if (!(await cancel.isVisible().catch(() => false))) break
    await cancel.click()
    await page.waitForTimeout(400)
  }
  for (let i = 0; i < 6; i++) {
    const b = page.locator('[role="dialog"] button[title="Close"]').last()
    if (!(await b.isVisible().catch(() => false))) break
    await b.click()
    await page.waitForTimeout(250)
  }
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
  await page.waitForSelector('[role="dialog"]')
  await page.waitForTimeout(500)
  return page.locator('[role="dialog"]').first()
}

const shot = async (page, file, locator) => {
  const target = locator ? await locator.elementHandle() : null
  if (target) await target.screenshot({ path: path.join(OUT, file) })
  else await page.screenshot({ path: path.join(OUT, file) })
  save(file)
}

try {
  /* ------------------------------------------------------------------ */
  /* Flat "Models" grid                                                  */
  /* ------------------------------------------------------------------ */
  let page = await newPage()
  let mgr = await openManager(page)
  await page.waitForTimeout(400)
  await shot(page, 'view-flat.png')
  await shot(page, 'view-flat-dialog.png', mgr)

  /* ------------------------------------------------------------------ */
  /* Folder (explorer) view, one level deep                              */
  /* ------------------------------------------------------------------ */
  await mgr.locator('button[title="Switch to Folder View"]').click()
  await page.waitForTimeout(800)
  const explorer = page.locator('[role="dialog"]').first()
  await explorer.locator('[data-card-main]').first().dblclick()
  await page.waitForTimeout(800)
  await shot(page, 'view-folders.png')
  await shot(page, 'view-folders-dialog.png', explorer)

  /* ------------------------------------------------------------------ */
  /* Model info: preview + base info + Description tab                   */
  /* ------------------------------------------------------------------ */
  await mgr.locator('button[title="Switch to Flat View"]').click()
  await page.waitForTimeout(800)
  mgr = page.locator('[role="dialog"]').first()
  await page.locator('[data-draggable-overlay]').first().click()
  await page.waitForTimeout(1200)
  const detail = page.locator('[role="dialog"]').last()
  await detail.locator('table').first().waitFor()
  await shot(page, 'model-info.png', detail)
  await detail.locator('button[aria-label="Edit model"]').click() // pencil -> edit mode
  await page.waitForTimeout(600)
  await shot(page, 'model-edit.png', detail)
  await detail.locator('button[title="Edit description"]').click()
  await page.waitForTimeout(500)
  await shot(page, 'model-edit-description.png', detail)
  await detail.locator('button[title="Close"]').click()
  await page.waitForTimeout(500)

  /* ------------------------------------------------------------------ */
  /* Folder picker popup (the nested dialog the stacking fix is about)   */
  /* ------------------------------------------------------------------ */
  await page.locator('[data-draggable-overlay]').first().click()
  await page.waitForTimeout(1000)
  const det2 = page.locator('[role="dialog"]').last()
  await det2.locator('button[aria-label="Edit model"]').click()
  await page.waitForTimeout(500)
  await det2.locator('form button:has(svg.lucide-folder-open)').first().click()
  await page.waitForTimeout(900)
  await shot(page, 'folder-picker.png')
  /* ------------------------------------------------------------------ */
  /* Create Download Task                                                */
  /* ------------------------------------------------------------------ */
  mgr = await ensureManager(page)
  await mgr.locator('button[title="Download List"]').click()
  await page.waitForTimeout(600)
  const dl = page.locator('[role="dialog"]').last()
  await dl.getByRole('button', { name: /Create Download Task/ }).click()
  await page.waitForTimeout(600)
  const create = page.locator('[role="dialog"]').last()
  await create
    .locator('input')
    .first()
    .fill(`http://127.0.0.1:${PORT}/remote/remote_model.safetensors`)
  await page.waitForTimeout(300)
  await create.locator('[aria-haspopup="menu"]').first().click()
  await page.waitForTimeout(500)
  await shot(page, 'download.png')
  await page.keyboard.press('Escape')
  await page.waitForTimeout(400)
  await create.locator('[aria-haspopup="menu"]').first().click()
  await page.waitForTimeout(500)
  // the menu is a portal on <body>, not a descendant of the dialog
  await page
    .locator('[role="menu"]')
    .last()
    .getByText('UNet/Diffusion Models', { exact: true })
    .click()
  await page.waitForTimeout(1500)
  await shot(page, 'download-resolved.png', create)

  /* ------------------------------------------------------------------ */
  /* Upload to HuggingFace (step 3, with the phase read-out)             */
  /* ------------------------------------------------------------------ */
  await page.evaluate(async () => {
    await fetch('/model-manager/download/setting', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'huggingface', value: btoa('hf_demo_token_1234567890') }),
    })
  })
  mgr = await ensureManager(page)
  await mgr.locator('button[title="Upload to HuggingFace"]').click()
  await page.waitForTimeout(900)
  const hf = page.locator('[role="dialog"]').last()
  await hf.locator('button:has-text("diffusion_models")').first().click()
  await page.waitForTimeout(600)
  await shot(page, 'hf-upload-step2.png', hf)
  await hf.getByText('anima-aesthetic-v1', { exact: true }).click()
  await page.waitForTimeout(600)
  await hf.locator('input').first().fill('rikunarita/HosekiAnima-V1')
  await hf
    .locator('#hf-private-repo')
    .click()
    .catch(() => {})
  await page.waitForTimeout(300)
  await shot(page, 'hf-upload.png', hf)
  await hf.getByRole('button', { name: 'Upload', exact: true }).click()
  await hf
    .locator('[role="progressbar"]')
    .waitFor({ timeout: 8000 })
    .catch(() => {})
  await page.waitForTimeout(700)
  await shot(page, 'hf-upload-progress.png', hf)
  await page.waitForTimeout(6000)
  await shot(page, 'hf-upload-toast.png')

  /* ------------------------------------------------------------------ */
  /* Panel-scoped loading                                                */
  /* ------------------------------------------------------------------ */
  await page.evaluate(() => {
    const api = window.comfyAPI.api.api
    const orig = api.fetchApi
    api.fetchApi = (url, opts) =>
      String(url).includes('/models/')
        ? new Promise(r => setTimeout(() => r(orig(url, opts)), 2500))
        : orig(url, opts)
  })
  mgr = await ensureManager(page)
  await mgr.locator('button[title="Refresh"]').click()
  await page.waitForTimeout(700)
  await shot(page, 'loading-panel.png')
  await page.waitForTimeout(2600)
  await page.close()

  /* ------------------------------------------------------------------ */
  /* Card-size settings dialog (reachable from the size dropdown).       */
  /* ComfyUI's own Settings page - where the API keys live - is host UI   */
  /* and cannot be rendered by the harness; capture it live instead.     */
  /* ------------------------------------------------------------------ */
  await page.close()
  page = await newPage()
  mgr = await openManager(page)
  await mgr.locator('[aria-haspopup="menu"]').nth(2).click()
  await page.waitForTimeout(500)
  await page.getByRole('menuitem', { name: /Custom Size/ }).click()
  await page.waitForTimeout(900)
  await shot(page, 'card-size.png', page.locator('[role="dialog"]').last())
  await page.close()

  /* ------------------------------------------------------------------ */
  /* Japanese UI                                                         */
  /* ------------------------------------------------------------------ */
  page = await newPage()
  await page.goto(`http://127.0.0.1:${PORT}/harness?locale=ja`)
  await page.waitForFunction(
    () => window.comfyAPI?.app?.app?.ui?.menuContainer?.children?.length > 0,
  )
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
  await page.waitForSelector('[role="dialog"]')
  await page.waitForFunction(() => document.querySelectorAll('[data-card-main]').length >= 3)
  await page.waitForTimeout(600)
  await shot(page, 'ja-view-flat.png')
  await page.locator('[data-draggable-overlay]').first().click()
  await page.waitForTimeout(1200)
  await shot(page, 'ja-model-info.png', page.locator('[role="dialog"]').last())
  await page.close()

  /* ------------------------------------------------------------------ */
  /* Toast stack + lightbox                                              */
  /* ------------------------------------------------------------------ */
  page = await newPage()
  mgr = await openManager(page)
  await page.evaluate(() => {
    const fire = (type, detail) => window.dispatchEvent(new CustomEvent('mm:' + type, { detail }))
    fire('hf_upload_complete', {
      taskId: 'a',
      repoId: 'rikunarita/HosekiAnima-V1',
      pathInRepo: 'HosekiAnima-V1.safetensors',
      skipped: false,
      deduplicated: false,
    })
    fire('hf_upload_complete', {
      taskId: 'b',
      repoId: 'rikunarita/HosekiAnima-V1',
      pathInRepo: 'same.safetensors',
      skipped: true,
      deduplicated: true,
      url: 'https://huggingface.co/rikunarita/HosekiAnima-V1/blob/main/same.safetensors',
    })
    fire('hf_upload_error', { taskId: 'c', error: 'Network is unreachable' })
  })
  await page.waitForTimeout(900)
  await shot(page, 'toast-stack.png')
  await page.waitForTimeout(400)

  // lightbox over the two-preview model
  for (let i = 0; i < 5; i++) {
    const b = page.locator('[role="dialog"] button[title="Close"]').last()
    if (!(await b.isVisible().catch(() => false))) break
    await b.click()
    await page.waitForTimeout(250)
  }
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
  await page.waitForSelector('[role="dialog"]')
  await page.waitForFunction(() => document.querySelectorAll('[data-card-main]').length >= 3)
  await page.locator('[data-draggable-overlay]').first().click()
  await page.waitForTimeout(1200)
  await page.locator('.preview-aspect').click({ position: { x: 60, y: 60 } })
  await page.waitForSelector('[data-mm-lightbox]')
  await page.waitForTimeout(500)
  await shot(page, 'lightbox.png')
  await page.keyboard.press('Escape')
  await page.close()

  /* ------------------------------------------------------------------ */
  /* Optional: recorded tour (hero)                                      */
  /* ------------------------------------------------------------------ */
  if (WITH_VIDEO) {
    const videoPage = await browser.newPage({
      viewport: { width: 1600, height: 1000 },
      recordVideo: { dir: path.join(OUT, '_video'), size: { width: 1600, height: 1000 } },
    })
    await videoPage.goto(`http://127.0.0.1:${PORT}/harness`)
    await videoPage.waitForFunction(
      () => window.comfyAPI?.app?.app?.ui?.menuContainer?.children?.length > 0,
    )
    await videoPage.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
    await videoPage.waitForSelector('[role="dialog"]')
    await videoPage.waitForTimeout(1500)
    const m = videoPage.locator('[role="dialog"]').first()
    await m.locator('button[title="Switch to Folder View"]').click()
    await videoPage.waitForTimeout(1200)
    await videoPage.locator('[data-card-main]').first().hover()
    await videoPage.waitForTimeout(2200)
    await videoPage.locator('[data-card-main]').first().dblclick()
    await videoPage.waitForTimeout(1200)
    await m.locator('button[title="Switch to Flat View"]').click()
    await videoPage.waitForTimeout(1500)
    await videoPage.locator('[data-draggable-overlay]').first().click()
    await videoPage.waitForTimeout(2000)
    await videoPage.close()
    const webm = readdirSync(path.join(OUT, '_video')).find(f => f.endsWith('.webm'))
    if (webm) {
      const src = path.join(OUT, '_video', webm)
      const dst = path.join(OUT, 'hero.webm')
      renameSync(src, dst)
      save('hero.webm')
      const gif = path.join(OUT, 'hero.gif')
      const r = spawnSync(
        'ffmpeg',
        [
          '-y',
          '-i',
          dst,
          '-vf',
          'fps=10,scale=900:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse',
          gif,
        ],
        { stdio: 'ignore' },
      )
      if (r.status === 0 && existsSync(gif)) save('hero.gif')
      else
        console.log(
          `  ffmpeg not available - convert manually:\n    ffmpeg -i docs/screenshots/hero.webm -vf "fps=10,scale=900:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" docs/screenshots/hero.gif`,
        )
    }
  }
} catch (error) {
  console.error('capture failed:', error?.message ?? error)
  process.exitCode = 1
} finally {
  await browser.close()
  server.kill()
}

console.log(`\n${written.length} asset(s) written to docs/screenshots/`)
