import { test, expect } from '@playwright/test'

// US5 journey: photo -> saved pending -> ready -> edit facts -> convert.
// Requires a running stack + seeded account; skipped without env config.
const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD

test.skip(!EMAIL || !PASSWORD, 'E2E_EMAIL/E2E_PASSWORD not configured')

test('captures page loads and shows the add control', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('邮箱').fill(EMAIL!)
  await page.getByLabel('密码').fill(PASSWORD!)
  await page.getByRole('button', { name: '登录' }).click()
  await page.goto('/captures')
  await expect(page.getByRole('heading', { name: '收藏' })).toBeVisible()
  await expect(page.getByText('拍照/上传')).toBeVisible()
})
