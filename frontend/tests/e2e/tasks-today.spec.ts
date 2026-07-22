import { test, expect } from '@playwright/test'

// US1 journey: login -> quick task -> edit -> complete -> reload.
// Requires a running stack + a seeded account (E2E_EMAIL / E2E_PASSWORD).
// Skipped automatically when those env vars are absent.
const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD

test.skip(!EMAIL || !PASSWORD, 'E2E_EMAIL/E2E_PASSWORD not configured')

test('quick task capture and completion survive reload', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('邮箱').fill(EMAIL!)
  await page.getByLabel('密码').fill(PASSWORD!)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/today/)

  const title = `E2E 任务 ${Date.now()}`
  await page.getByLabel('快速添加任务').fill(title)
  await page.getByRole('button', { name: '添加' }).click()
  await expect(page.getByText(title)).toBeVisible()

  // Reload: the task persists (durable capture, no AI dependency).
  await page.reload()
  await expect(page.getByText(title)).toBeVisible()

  // Complete it.
  await page.getByRole('button', { name: `完成 ${title}` }).click()
  await expect(page.getByText(title)).toBeVisible()
})
