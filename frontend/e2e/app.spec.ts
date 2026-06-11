/**
 * Full-stack E2E (spec Stage 9): login → dashboard data → chart with
 * indicator → run backtest → view results. Runs against the compose stack
 * seeded with synthetic candles (no Binance network dependency).
 */
import { expect, test } from '@playwright/test'

const PASSWORD = process.env.E2E_PASSWORD ?? 'cryptoquant-dev'

test.describe.configure({ mode: 'serial' })

async function login(page: import('@playwright/test').Page) {
  await page.goto('/')
  await page.waitForSelector('input[aria-label="Password"]', { timeout: 30000 })
  await page.fill('input[aria-label="Password"]', PASSWORD)
  await page.click('button:has-text("Sign in")')
  await page.waitForSelector('nav', { timeout: 30000 })
}

test('login rejects a wrong password', async ({ page }) => {
  await page.goto('/')
  await page.waitForSelector('input[aria-label="Password"]')
  await page.fill('input[aria-label="Password"]', 'definitely-wrong')
  await page.click('button:has-text("Sign in")')
  await expect(page.getByRole('alert')).toContainText('Invalid password')
})

test('login → dashboard shows watchlist data', async ({ page }) => {
  await login(page)
  await page.waitForSelector('table tbody tr', { timeout: 30000 })
  const btcRow = page.locator('tbody tr', { hasText: 'BTC' }).first()
  await expect(btcRow).toBeVisible()
  // Price cell populated (not the em-dash placeholder)
  await expect(btcRow.locator('td').nth(2)).not.toHaveText('—')
})

test('chart renders candles and an indicator overlay', async ({ page }) => {
  await login(page)
  await page.click('a:has-text("Chart")')
  await page.waitForSelector('[data-testid="candle-chart"] canvas', {
    timeout: 30000,
  })
  const before = await page.locator('canvas').count()
  await page.getByRole('button', { name: 'RSI', exact: true }).click()
  await expect
    .poll(async () => page.locator('canvas').count(), { timeout: 20000 })
    .toBeGreaterThan(before) // RSI pane adds canvases
})

test('run a backtest and view results', async ({ page }) => {
  await login(page)
  await page.click('a:has-text("Backtest")')
  await page.waitForSelector('input[aria-label="Fast period"]', {
    timeout: 30000,
  })
  await page.getByLabel('Fast period').fill('10')
  await page.getByRole('button', { name: 'Run backtest' }).click()
  await page.waitForSelector('[data-testid="metrics-cards"]', {
    timeout: 60000,
  })
  await expect(page.getByTestId('equity-chart')).toBeVisible()
  await expect(page.getByTestId('trades-table')).toBeVisible()
  await expect(page.getByTestId('monthly-heatmap')).toBeVisible()
})

test('saved backtest reloads from the list', async ({ page }) => {
  await login(page)
  await page.click('a:has-text("Backtest")')
  await page.waitForSelector('[data-testid="saved-backtests"] tr', {
    timeout: 30000,
  })
  await page
    .locator('[data-testid="saved-backtests"] >> text=load')
    .first()
    .click()
  await page.waitForSelector('[data-testid="metrics-cards"]', {
    timeout: 30000,
  })
})
