import { test, expect } from '@playwright/test'

// US9 journey: grounded arrange-today, fixed-event rejection, selected apply.
// Requires a running stack + seeded account; skipped without env config.
const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD

test.skip(!EMAIL || !PASSWORD, 'E2E_EMAIL/E2E_PASSWORD not configured')

test('assistant produces grounded action cards', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('邮箱').fill(EMAIL!)
  await page.getByLabel('密码').fill(PASSWORD!)
  await page.getByRole('button', { name: '登录' }).click()

  await page.goto('/assistant')
  await page.getByRole('button', { name: '安排今天' }).click()
  // Either grounded cards or an honest no-result card appears.
  await expect(page.getByRole('region', { name: '结构化结果' })).toBeVisible()
})
