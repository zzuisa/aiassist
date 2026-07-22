import { test, expect } from '@playwright/test'

// US3 journey: create habit -> check in -> skip -> statistics.
// Requires a running stack + seeded account; skipped without env config.
const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD

test.skip(!EMAIL || !PASSWORD, 'E2E_EMAIL/E2E_PASSWORD not configured')

test('create habit and check in', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('邮箱').fill(EMAIL!)
  await page.getByLabel('密码').fill(PASSWORD!)
  await page.getByRole('button', { name: '登录' }).click()

  await page.goto('/habits')
  await page.getByRole('button', { name: '新建习惯' }).click()
  const name = `晨跑 ${Date.now()}`
  await page.getByLabel('习惯名称').fill(name)
  await page.getByRole('button', { name: '创建' }).click()
  await expect(page.getByText(name)).toBeVisible()

  await page.getByRole('button', { name: `打卡 ${name}` }).click()
  await expect(page.getByText('已完成')).toBeVisible()
})
