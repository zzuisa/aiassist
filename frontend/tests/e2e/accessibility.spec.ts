import { test, expect } from '@playwright/test'

// Accessibility & responsive gates: 360px no horizontal scroll, keyboard focus,
// 44px targets, non-color status. Requires a running stack + seeded account.
const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD

test.skip(!EMAIL || !PASSWORD, 'E2E_EMAIL/E2E_PASSWORD not configured')

test.use({ viewport: { width: 360, height: 780 } })

test('no horizontal scroll at 360px', async ({ page }) => {
  await page.goto('/login')
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  )
  expect(overflow).toBe(false)
})

test('login form is keyboard reachable', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('邮箱').focus()
  await expect(page.getByLabel('邮箱')).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByLabel('密码')).toBeFocused()
})

test('primary tap targets are at least 44px', async ({ page }) => {
  await page.goto('/login')
  const box = await page.getByRole('button', { name: '登录' }).boundingBox()
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(44)
})
