import { test, expect } from '@playwright/test'

// US8 journey: source -> draft -> AI diff -> publish -> anonymous read -> unpublish.
// Requires a running stack + seeded account; skipped without env config.
const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD

test.skip(!EMAIL || !PASSWORD, 'E2E_EMAIL/E2E_PASSWORD not configured')

test('create, edit and publish a post', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('邮箱').fill(EMAIL!)
  await page.getByLabel('密码').fill(PASSWORD!)
  await page.getByRole('button', { name: '登录' }).click()

  await page.goto('/posts')
  await page.getByRole('button', { name: '新建文章' }).click()
  await expect(page).toHaveURL(/\/posts\//)

  await page.getByLabel('正文').fill('# 我的第一篇\n\n正文内容。')
  await page.getByRole('button', { name: '发布' }).click()
  await expect(page.getByText('已发布')).toBeVisible()
})
