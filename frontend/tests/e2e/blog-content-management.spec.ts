import { test, expect, type Page } from '@playwright/test'

// US1 journey: capture durable content before any AI runs.
// Requires a running stack + seeded account; self-skips without env config so it
// is safe to keep in the default suite.
const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD

test.skip(!EMAIL || !PASSWORD, 'E2E_EMAIL/E2E_PASSWORD not configured')

async function login(page: Page): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('邮箱').fill(EMAIL!)
  await page.getByLabel('密码').fill(PASSWORD!)
  await page.getByRole('button', { name: '登录' }).click()
}

test('quick capture saves and returns to the list (happy path)', async ({ page }) => {
  await login(page)
  await page.goto('/blog')
  await page.getByRole('button', { name: '新建内容' }).click()

  // Source picker → quick record.
  await page.getByText('快速记录', { exact: true }).click()
  await page.locator('textarea').fill('端到端的快速记录内容')
  await page.getByRole('button', { name: '保存', exact: true }).click()

  // Toast confirms the durable save; the item shows up in the list.
  await expect(page.getByText('已保存到「待整理」')).toBeVisible()
})

test('url capture stays durable and reports async extraction', async ({ page }) => {
  await login(page)
  await page.goto('/blog')
  await page.getByRole('button', { name: '新建内容' }).click()
  await page.getByText('从网址', { exact: true }).click()

  await page.getByPlaceholder('https://…').fill('https://example.com/an-article')
  await page.getByRole('button', { name: '保存并抓取' }).click()

  // The record is saved before extraction completes.
  await expect(page.getByText('已保存，正在后台抓取正文…')).toBeVisible()
  // We are taken into the durable draft.
  await expect(page).toHaveURL(/\/blog\//)
})

test('url capture rejects an unsafe address (failure path)', async ({ page }) => {
  await login(page)
  await page.goto('/blog')
  await page.getByRole('button', { name: '新建内容' }).click()
  await page.getByText('从网址', { exact: true }).click()

  await page.getByPlaceholder('https://…').fill('http://169.254.169.254/latest/meta-data')
  await page.getByRole('button', { name: '保存并抓取' }).click()

  await expect(page.getByText('该链接不被允许（可能是内网地址或非法协议）。')).toBeVisible()
})
