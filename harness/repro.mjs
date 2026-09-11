/**
 * Reproduction driver for the two reported bugs (run BEFORE fixing):
 *   R1 — Create Download Task: URL -> model type -> Download => nothing happens
 *   R2 — HuggingFace upload: no progress bar, task dies with the dialog
 *
 * Usage: node harness/repro.mjs
 */
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const PORT = 8861
const server = spawn('python3', ['harness/serve.py', '--port', String(PORT)], {
  stdio: ['ignore', 'pipe', 'pipe'],
})
server.stderr.on('data', d => process.stderr.write(`[serve] ${d}`))
for (let i = 0; i < 60; i++) {
  try {
    const res = await fetch(`http://127.0.0.1:${PORT}/harness`)
    if (res.ok) break
  } catch {
    /* not up yet */
  }
  await new Promise(r => setTimeout(r, 250))
}

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
page.on('console', m => {
  if (m.type() === 'error') console.log('[console.error]', m.text().slice(0, 220))
})
page.on('pageerror', e => console.log('[pageerror]', e.message.slice(0, 220)))
page.on('response', r => {
  if (r.request().method() === 'POST' || r.status() >= 400)
    console.log(
      `[http] ${r.request().method()} ${r.url().replace('http://127.0.0.1:' + PORT, '')} -> ${r.status()}`,
    )
})

const base = `http://127.0.0.1:${PORT}`
await page.goto(`${base}/harness`)
await page.waitForFunction(() => window.comfyAPI?.app?.app?.ui?.menuContainer?.children?.length > 0)
await page.evaluate(() => window.dispatchEvent(new CustomEvent('open-model-manager')))
await page.waitForSelector('[role="dialog"]')

/* ---------------------------------------------------------------- R1 ---- */
console.log('=== R1: Create Download Task (direct link) ===')
await page.locator('button[title="Download List"]').click()
const dl = page.locator('[role="dialog"]').last()
await dl.getByRole('button', { name: /Create Download Task/ }).click()
const create = page.locator('[role="dialog"]').last()
await create.waitFor()

const url = `${base}/remote/remote_model.safetensors`
await create.locator('input').first().fill(url)
await create.locator('input').first().press('Enter')
await page.waitForTimeout(600)

// model-type dropdown (the direct-file banner select)
const typeTrigger = create.locator('[aria-haspopup="menu"]').first()
await typeTrigger.click()
await page.locator('[role="menu"]').getByText('UNet/Diffusion Models', { exact: true }).click()
await page.waitForTimeout(800)

const downloadBtn = create.getByRole('button', { name: 'Download', exact: true })
console.log('R1 download disabled?', await downloadBtn.isDisabled())
await downloadBtn.click()
await page.waitForTimeout(2500)

console.log('R1 create dialog still open?', await create.isVisible().catch(() => false))
const tasks = await (await fetch(`${base}/model-manager/download/task`)).json()
console.log(
  'R1 task list:',
  JSON.stringify(tasks.data?.map(t => [t.taskId.slice(0, 6), t.status, t.fullname])),
)
const models = await (await fetch(`${base}/model-manager/models/checkpoints`)).json()
console.log(
  'R1 checkpoints:',
  JSON.stringify(models.data?.filter(m => !m.isFolder).map(m => m.subFolder + '/' + m.basename)),
)

/* ---------------------------------------------------------------- R2 ---- */
console.log('=== R2: HuggingFace upload ===')
// close leftovers, open the HF dialog from the manager header
for (const title of ['Close', 'Close']) {
  const btn = page.locator(`[role="dialog"] button[title="${title}"]`).last()
  if (await btn.isVisible().catch(() => false)) await btn.click()
  await page.waitForTimeout(400)
}
await page.locator('[role="dialog"] button[title="Upload to HuggingFace"]').click()
const hf = page.locator('[role="dialog"]').last()
await hf.waitFor()
await hf.locator('button:has-text("diffusion_models")').first().click()
await page.waitForTimeout(600)
// step 2: pick first model card
await hf.locator('.preview-aspect').first().click()
await page.waitForTimeout(600)
await hf.locator('input').first().fill('rikunarita/repro-repo')
const uploadBtn = hf.getByRole('button', { name: 'Upload', exact: true })
console.log('R2 upload disabled?', await uploadBtn.isDisabled())
await uploadBtn.click()
await page.waitForTimeout(1200)
const barVisible = await hf
  .locator('[role="dialog"] .mm-indeterminate, [role="dialog"] [role="progressbar"]')
  .first()
  .isVisible()
  .catch(() => false)
console.log('R2 progress bar visible while open?', barVisible)
await page.screenshot({ path: 'harness/shots/repro-hf-open.png' })

// close the dialog mid-upload, exactly like the report
await hf.locator('button[title="Close"]').click()
console.log('R2 dialog closed at t≈1.5s, waiting for the fake 4s upload...')
await page.waitForTimeout(6000)
const hfState = await (await fetch(`${base}/probe/hf`)).json()
const events = await (await fetch(`${base}/probe/events`)).json()
console.log('R2 fake HF uploads:', JSON.stringify(hfState.uploads))
console.log('R2 ws events:', JSON.stringify(events.filter(e => String(e).includes('hf'))))

await browser.close()
server.kill()
