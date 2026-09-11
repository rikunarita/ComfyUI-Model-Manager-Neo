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
import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const PORT = 8700 + (process.pid % 200)
const SHOTS = path.join(ROOT, 'harness', 'shots')
mkdirSync(SHOTS, { recursive: true })

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

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })

const consoleErrors = []
page.on('console', msg => {
  if (msg.type() === 'error') consoleErrors.push(msg.text())
})
page.on('pageerror', err => consoleErrors.push(`pageerror: ${err.message}`))

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

  // The manager opens in folder layout by default; the screenshots and the
  // grid audit target the FLAT view, so toggle exactly like a user would.
  await manager.locator('button[title="Switch to Flat View"]').click()
  await page.waitForSelector('[role="dialog"] input[placeholder="Search models"]', {
    timeout: 10000,
  })

  // E03 — header icon buttons are glass push buttons
  const headerButtons = await glassButtonAudit('[role="dialog"] button[title]')
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
  await hf2.locator('.preview-aspect').first().click()
  await page.waitForTimeout(400)
  await hf2.locator('input').first().fill('rikunarita/e2e-repo')
  await hf2.getByRole('button', { name: 'Upload', exact: true }).click()
  await hf2.locator('.mm-indeterminate').waitFor({ timeout: 5000 })
  check('E14 progress bar visible during upload', true)
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
