// End-to-end tests against the real FastAPI backend and the real catalog.
// Only the loading, error and image-success scenarios intercept network calls.
import { expect, test } from '@playwright/test'

const occasionInput = (page) => page.getByLabel("What's the occasion?")
const findButton = (page) => page.getByRole('button', { name: /find gifts|finding/i })
const cards = (page) => page.getByTestId('product-card')

async function prices(page) {
  return page.getByTestId('final-price').evaluateAll((els) => els.map((e) => Number(e.dataset.value)))
}

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('initial page shows heading, labelled input and idle state', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Find the Perfect Gift' })).toBeVisible()
  await expect(page.getByText("Tell us what you're celebrating. We'll find something special.")).toBeVisible()
  await expect(occasionInput(page)).toBeVisible()
  await expect(findButton(page)).toBeDisabled() // empty input cannot be submitted
  await expect(page.getByText('Your shortlist will appear here')).toBeVisible()
})

test('typing an occasion and clicking the search button shows ranked cards below the input', async ({ page }) => {
  await occasionInput(page).fill("Valentine's Day")
  await findButton(page).click()
  await expect(page.getByRole('heading', { name: /ideas for Valentine's Day/ })).toBeVisible()
  const count = await cards(page).count()
  expect(count).toBeGreaterThanOrEqual(8)

  const first = cards(page).first()
  await expect(first.getByRole('heading', { level: 3 })).not.toBeEmpty()
  await expect(first.getByText('#1')).toBeVisible()
  await expect(first.getByText(/% match/)).toBeVisible()
  await expect(first.getByText(/Recommended for Valentine's Day/)).toBeVisible()
  await expect(first.getByText(/in stock|left/)).toBeVisible()
  await expect(first.getByTestId('final-price')).toBeVisible()

  // Results render on the same page, below the search input.
  const inputBox = await occasionInput(page).boundingBox()
  const cardBox = await first.boundingBox()
  expect(cardBox.y).toBeGreaterThan(inputBox.y)
  expect(page.url()).toContain('q=Valentine')
})

test('pressing Enter submits the search', async ({ page }) => {
  await occasionInput(page).fill('Gift for a child')
  await occasionInput(page).press('Enter')
  await expect(page.getByRole('heading', { name: /ideas for Kids/ })).toBeVisible()
  await expect(cards(page).first().getByText('Toys & Kids')).toBeVisible()
})

test('suggestion chips run a search and fill the input', async ({ page }) => {
  for (const occasion of ['Diwali', 'Office Party']) {
    await page.getByRole('button', { name: occasion, exact: true }).click()
    await expect(page.getByRole('heading', { name: new RegExp(`ideas for ${occasion}`) })).toBeVisible()
    await expect(occasionInput(page)).toHaveValue(occasion)
  }
  await expect(cards(page).first()).toContainText(/pen/i)
})

test('loading state shows skeletons and a busy search button', async ({ page }) => {
  await page.route('**/api/recommend', async (route) => {
    await new Promise((r) => setTimeout(r, 1500))
    await route.continue()
  })
  await occasionInput(page).fill('Birthday')
  await findButton(page).click()
  await expect(page.getByLabel('Loading recommendations')).toBeVisible()
  await expect(page.getByRole('button', { name: /finding/i })).toBeDisabled()
  await expect(cards(page).first()).toBeVisible()
  await expect(page.getByLabel('Loading recommendations')).toHaveCount(0)
})

test('unknown occasion shows the empty state without unrelated products', async ({ page }) => {
  await occasionInput(page).fill('gaming laptop')
  await findButton(page).click()
  await expect(page.getByText('No relevant products found for this occasion. Try another occasion.')).toBeVisible()
  await expect(cards(page)).toHaveCount(0)
  // Suggested occasions in the empty state are clickable.
  await page.getByRole('button', { name: 'Housewarming', exact: true }).click()
  await expect(page.getByRole('heading', { name: /ideas for Housewarming/ })).toBeVisible()
})

test('API failure shows an error state and retry recovers', async ({ page }) => {
  await page.route('**/api/recommend', (route) => route.abort('connectionrefused'))
  await occasionInput(page).fill('Wedding')
  await findButton(page).click()
  await expect(page.getByText('Something went wrong')).toBeVisible()
  await expect(page.getByText(/Can't reach the recommendation service/)).toBeVisible()

  await page.unroute('**/api/recommend')
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('heading', { name: /ideas for Wedding/ })).toBeVisible()
})

test('backend validation errors are shown in the error state', async ({ page }) => {
  await page.route('**/api/recommend', (route) =>
    route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: 'Occasion must not be empty.' }) }))
  await occasionInput(page).fill('Birthday')
  await findButton(page).click()
  await expect(page.getByText('Occasion must not be empty.')).toBeVisible()
})

test('price filters are sent to the API and respected by the results', async ({ page }) => {
  await occasionInput(page).fill("Valentine's Day")
  await findButton(page).click()
  await expect(cards(page).first()).toBeVisible()

  await page.getByRole('button', { name: /filters/i }).click()
  const request = page.waitForRequest((r) => r.url().endsWith('/api/recommend') && r.postDataJSON().max_price === 1000)
  await page.getByLabel('Max price (₹)').fill('1000')
  const body = (await request).postDataJSON()
  expect(body.max_price).toBe(1000)
  await expect(page.getByText('Budget up to ₹1,000')).toBeVisible()
  const filtered = await prices(page)
  expect(filtered.length).toBeGreaterThan(0)
  expect(filtered.every((p) => p <= 1000)).toBe(true)

  const minRequest = page.waitForRequest((r) => r.url().endsWith('/api/recommend') && r.postDataJSON().min_price === 500)
  await page.getByLabel('Min price (₹)').fill('500')
  await minRequest
  await expect(page.getByText(/Budget from ₹500 up to ₹1,000/)).toBeVisible()
  const ranged = await prices(page)
  expect(ranged.every((p) => p >= 500 && p <= 1000)).toBe(true)
})

test('impossible price range shows the filter empty state', async ({ page }) => {
  await occasionInput(page).fill('Birthday')
  await findButton(page).click()
  await expect(cards(page).first()).toBeVisible()
  await page.getByRole('button', { name: /filters/i }).click()
  await page.getByLabel('Max price (₹)').fill('1')
  await expect(page.getByText(/No products match the selected filters/)).toBeVisible()
})

test('category filter restricts results and clear resets it', async ({ page }) => {
  await occasionInput(page).fill('Anniversary')
  await findButton(page).click()
  await expect(cards(page).first()).toBeVisible()
  await page.getByRole('button', { name: /filters/i }).click()

  const select = page.getByLabel(/Category/)
  const jewellery = await select.locator('option', { hasText: /^Jewellery/ }).getAttribute('value')
  const response = page.waitForResponse((r) => r.url().endsWith('/api/recommend')
    && r.request().postDataJSON().category === jewellery)
  await select.selectOption(jewellery)
  const data = await (await response).json()
  expect(data.total_results).toBeGreaterThan(0)
  expect(data.recommendations.every((r) => r.category_id === jewellery)).toBe(true)
  await expect(cards(page)).toHaveCount(data.total_results)

  const cleared = page.waitForResponse((r) => r.url().endsWith('/api/recommend')
    && r.request().postDataJSON().category === null)
  await page.getByRole('button', { name: 'Clear' }).click()
  await cleared
  await expect(select).toHaveValue('')
})

test('budget written in the query is applied', async ({ page }) => {
  await occasionInput(page).fill('Something under ₹1,000')
  await findButton(page).click()
  await expect(page.getByText('Budget up to ₹1,000')).toBeVisible()
  expect((await prices(page)).every((p) => p <= 1000)).toBe(true)
})

test('product images use the catalog URL and fall back when it fails', async ({ page }) => {
  await occasionInput(page).fill('Diwali')
  await findButton(page).click()
  const first = cards(page).first()
  await expect(first.getByTestId('image-fallback')).toBeVisible() // catalog host currently returns 404
  await expect(first.getByTestId('image-fallback')).toContainText('Image unavailable')
})

test('product images render when the image host responds', async ({ page }) => {
  // 1x1 PNG served for the catalog image host to prove the <img> path uses mainImage unchanged.
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg==', 'base64')
  await page.route('https://s3aws.emilo.in/**', (route) => route.fulfill({ status: 200, contentType: 'image/png', body: png }))
  await occasionInput(page).fill('Diwali')
  await findButton(page).click()
  const img = cards(page).first().locator('img')
  await expect(img).toBeVisible()
  expect(await img.getAttribute('src')).toMatch(/^https:\/\/s3aws\.emilo\.in\/products\//)
  await expect(cards(page).first().getByTestId('image-fallback')).toHaveCount(0)
})

test('shared ?q= link runs the search on load', async ({ page }) => {
  await page.goto('/?q=Housewarming')
  await expect(page.getByRole('heading', { name: /ideas for Housewarming/ })).toBeVisible()
  await expect(occasionInput(page)).toHaveValue('Housewarming')
})

test.describe('mobile layout', () => {
  test.use({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true })

  test('search works and nothing overflows horizontally', async ({ page }) => {
    await occasionInput(page).fill('Birthday')
    await findButton(page).click()
    await expect(cards(page).first()).toBeVisible()
    const { scrollWidth, innerWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth,
    }))
    expect(scrollWidth).toBeLessThanOrEqual(innerWidth)
    const box = await cards(page).first().boundingBox()
    expect(box.x).toBeGreaterThanOrEqual(0)
    expect(box.x + box.width).toBeLessThanOrEqual(375)
  })
})
