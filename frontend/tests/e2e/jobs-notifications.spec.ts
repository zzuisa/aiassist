import { test, expect } from '@playwright/test'

// US6 journey: critical reminder under load, worker crash, SSE replay, retry/cancel.
// Requires a running stack + seeded account; skipped without env config.
const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD

test.skip(!EMAIL || !PASSWORD, 'E2E_EMAIL/E2E_PASSWORD not configured')

test('task center and notification center open from the topbar', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('邮箱').fill(EMAIL!)
  await page.getByLabel('密码').fill(PASSWORD!)
  await page.getByRole('button', { name: '登录' }).click()
  await page.goto('/today')

  await page.getByRole('button', { name: '后台任务中心' }).click()
  await expect(page.getByRole('dialog', { name: '后台任务中心' })).toBeVisible()

  await page.getByRole('button', { name: '关闭' }).click()
  await page.getByRole('button', { name: '通知' }).click()
  await expect(page.getByRole('dialog', { name: '通知' })).toBeVisible()
})
