// Regenerates ../screenshots from the running app (backend :8000, frontend :5173).
// Usage: node e2e/capture-screenshots.mjs
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'

const BASE = 'http://localhost:5173'
const OUT = new URL('../../screenshots/', import.meta.url)
const shots = [
  ['01-occasion-input.png', '/', { width: 1440, height: 1000 }, false],
  ['02-results-valentines.png', "/?q=Valentine's Day", { width: 1440, height: 1000 }, true],
  ['03-results-diwali.png', '/?q=Diwali', { width: 1440, height: 1000 }, true],
  ['04-free-text-budget.png', '/?q=Something romantic for my girlfriend under 1500', { width: 1440, height: 1500 }, false],
  ['05-empty-state.png', '/?q=gaming laptop', { width: 1440, height: 1000 }, false],
  ['06-mobile.png', '/?q=Gift for a child', { width: 390, height: 844 }, false],
  ['07-results-graduation.png', '/?q=Graduation', { width: 1440, height: 1500 }, false],
]

const browser = await chromium.launch({ channel: 'chrome' })
for (const [file, path, viewport, fullPage] of shots) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 })
  await page.goto(BASE + encodeURI(path))
  if (path.includes('?q=')) {
    await page.getByTestId('product-card').first().or(page.getByText('No matches yet')).waitFor({ timeout: 30000 })
  }
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(800) // let card entrance animations finish
  await page.screenshot({ path: fileURLToPath(new URL(file, OUT)), fullPage })
  console.log('wrote', file)
  await page.close()
}
// Product detail panel
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 })
  await page.goto(BASE + encodeURI("/?q=Valentine's Day"))
  await page.getByTestId('product-card').first().getByRole('button', { name: 'View details', exact: true }).click()
  await page.getByRole('dialog').waitFor()
  await page.waitForTimeout(600)
  await page.screenshot({ path: fileURLToPath(new URL('08-product-detail.png', OUT)) })
  console.log('wrote 08-product-detail.png')
  await page.close()
}
await browser.close()
