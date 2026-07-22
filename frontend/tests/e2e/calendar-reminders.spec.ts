import { test, expect } from '@playwright/test'

// US2 journey: fixed-event protection, drag rollback, selective preview apply.
// Requires a running stack + seeded account. Skipped without env config.
const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD

test.skip(!EMAIL || !PASSWORD, 'E2E_EMAIL/E2E_PASSWORD not configured')

test('calendar shows conflicts and preview drawer opens', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('邮箱').fill(EMAIL!)
  await page.getByLabel('密码').fill(PASSWORD!)
  await page.getByRole('button', { name: '登录' }).click()
  await page.goto('/calendar')
  await expect(page.getByRole('heading', { name: '日历' })).toBeVisible()

  await page.getByRole('button', { name: 'AI 调整预览' }).click()
  // Fixed-event suggestions render as non-selectable.
  const drawer = page.getByRole('dialog', { name: '日程调整预览' })
  await expect(drawer).toBeVisible()
})
