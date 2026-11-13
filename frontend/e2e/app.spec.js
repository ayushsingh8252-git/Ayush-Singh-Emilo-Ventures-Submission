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

test('product images fall back to the representative photo when the catalog URL fails', async ({ page }) => {
  await occasionInput(page).fill('Diwali')
  await findButton(page).click()
  const first = cards(page).first()
  // The catalog host currently returns 404, so the downloaded Commons photo is shown instead.
  await expect(first.locator('img')).toHaveAttribute('src', /^\/product-images\/[\w-]+\.jpg$/)
  await expect(first.locator('img')).toBeVisible()
  await expect(first.getByText('Representative photo')).toBeVisible()
  await expect(first.getByTestId('image-fallback')).toHaveCount(0)
})

test('generated artwork shows when no photo can be loaded', async ({ page }) => {
  await page.route(/\/product-images\//, (route) => route.fulfill({ status: 404 }))
  await occasionInput(page).fill('Diwali')
  await findButton(page).click()
  const first = cards(page).first()
  await expect(first.getByTestId('image-fallback')).toBeVisible()
  await expect(first.getByTestId('image-fallback')).toContainText(await first.locator('h3').innerText())
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

test('navigation bar shows the live engine status', async ({ page }) => {
  await expect(page.getByTestId('engine-status')).toHaveText('AI ranking active')
  await expect(page.getByRole('link', { name: 'API docs' })).toHaveAttribute('href', /\/docs$/)
})

test('sorting reorders results but keeps relevance ranks', async ({ page }) => {
  await occasionInput(page).fill("Valentine's Day")
  await findButton(page).click()
  await expect(cards(page).first()).toBeVisible()
  await page.getByLabel('Sort results').selectOption('price-asc')
  const ascending = await prices(page)
  expect(ascending).toEqual([...ascending].sort((a, b) => a - b))
  await page.getByLabel('Sort results').selectOption('price-desc')
  const descending = await prices(page)
  expect(descending).toEqual([...descending].sort((a, b) => b - a))
  await page.getByLabel('Sort results').selectOption('relevance')
  await expect(cards(page).first().getByText('#1')).toBeVisible()
})

test('product detail panel shows full explanation and score breakdown', async ({ page }) => {
  await occasionInput(page).fill('Anniversary')
  await findButton(page).click()
  const first = cards(page).first()
  const name = await first.getByRole('heading', { level: 3 }).innerText()
  await first.getByRole('button', { name: 'View details', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('heading', { name })).toBeVisible()
  await expect(dialog.getByText('Semantic similarity')).toBeVisible()
  await expect(dialog.getByText('Keyword match')).toBeVisible()
  await expect(dialog.getByText('Occasion fit')).toBeVisible()
  await expect(dialog.getByText(/Recommended for Anniversary/)).toBeVisible()
  await expect(dialog.getByTestId('photo-credit')).toContainText('Wikimedia Commons')
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
})

test('active filter chips can be removed', async ({ page }) => {
  await occasionInput(page).fill('Birthday')
  await findButton(page).click()
  await expect(cards(page).first()).toBeVisible()
  await page.getByRole('button', { name: /filters/i }).click()
  await page.getByLabel('Max price (₹)').fill('800')
  await expect(page.getByText('Max ₹800')).toBeVisible()
  const cleared = page.waitForRequest((r) => r.url().endsWith('/api/recommend') && r.postDataJSON().max_price === null)
  await page.getByRole('button', { name: 'Remove Max ₹800 filter' }).click()
  await cleared
  await expect(page.getByText('Max ₹800')).toHaveCount(0)
})

// The LLM layer is disabled for the test servers; these tests take a REAL response from the
// backend and mark it as LLM-understood, to check how the UI presents it.
async function markAsLlm(page, overrides) {
  await page.route('**/api/recommend', async (route) => {
    const response = await route.fetch()
    const json = await response.json()
    json.interpretation = { ...json.interpretation, ...overrides }
    await route.fulfill({ response, json })
  })
}

test('LLM-understood queries show recipient, preferences and the Gemini badge', async ({ page }) => {
  await markAsLlm(page, {
    understanding_mode: 'llm', llm_provider: 'gemini', llm_model: 'gemini-3.5-flash-lite',
    recipient: 'girlfriend', preferences: ['romantic', 'thoughtful'],
  })
  const request = page.waitForRequest((r) => r.url().endsWith('/api/recommend'))
  await occasionInput(page).fill('Suggest a romantic gift for my girlfriend under ₹2,000')
  await findButton(page).click()
  expect((await request).postDataJSON().query).toBe('Suggest a romantic gift for my girlfriend under ₹2,000')
  const understanding = page.getByTestId('understanding')
  await expect(understanding.getByText('Understood by Gemini')).toBeVisible()
  await expect(understanding.getByText('For: girlfriend')).toBeVisible()
  await expect(understanding.getByText('thoughtful')).toBeVisible()
  await expect(page.getByText('Budget up to ₹2,000')).toBeVisible()
  expect((await prices(page)).every((p) => p <= 2000)).toBe(true)
})

test('LLM fallback is explained to the user', async ({ page }) => {
  await markAsLlm(page, { understanding_mode: 'rules', llm_fallback_reason: 'timeout' })
  await occasionInput(page).fill('Anniversary')
  await findButton(page).click()
  await expect(page.getByText('Rule-based understanding used because the AI service timed out.')).toBeVisible()
  await expect(cards(page).first()).toBeVisible()
})
