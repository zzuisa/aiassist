import { test, expect, type Page } from '@playwright/test'

// Accessibility & responsive gates: 360px no horizontal scroll, keyboard focus,
// 44px targets, non-color status. Requires a running stack + seeded account.
const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD

test.skip(!EMAIL || !PASSWORD, 'E2E_EMAIL/E2E_PASSWORD not configured')

test.use({ viewport: { width: 360, height: 780 } })

async function login(page: Page): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('邮箱').fill(EMAIL!)
  await page.getByLabel('密码').fill(PASSWORD!)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/today/)
  await page.getByRole('button', { name: '关闭更新公告' }).click()
}

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

test('blog dialog traps focus and restores it to the keyboard invoker', async ({ page }) => {
  await login(page)
  await page.goto('/blog')
  const opener = page.getByRole('button', { name: '新建内容' })
  await opener.focus()
  await page.keyboard.press('Enter')

  const dialog = page.getByRole('dialog', { name: '新建内容' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('button', { name: '关闭' })).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(dialog.getByRole('button', { name: '快速记录' })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(dialog.getByRole('button', { name: '关闭' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(opener).toBeFocused()
})

test('editor controls and textual save status work with keyboard and screen readers', async ({ page }) => {
  await login(page)
  await page.goto('/blog')
  await page.getByRole('button', { name: '新建内容' }).click()
  await page.getByRole('button', { name: '空白文章' }).click()
  await expect(page).toHaveURL(/\/blog\/[0-9a-f-]+$/)

  const sourceMode = page.getByRole('button', { name: '源码' })
  await sourceMode.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('textarea.md-source')).toBeVisible()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: '富文本' })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: '分栏' })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: '预览' })).toBeFocused()

  await sourceMode.click()
  await page.locator('textarea.md-source').fill('# 可访问章节\n\n正文')
  await expect(page.locator('.save-state[role="status"]')).toHaveText(/保存中|已保存/)
  await expect(page.getByRole('button', { name: '可访问章节' })).toBeVisible()
})

for (const width of [360, 375, 390]) {
  test(`bottom navigation stays reachable without overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 780 })
    await login(page)
    await page.goto('/blog')
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth))
      .toBeLessThanOrEqual(width)
    const nav = page.getByRole('navigation', { name: '主导航' })
    await expect(nav).toBeVisible()
    const box = await nav.boundingBox()
    expect(box?.x ?? -1).toBeGreaterThanOrEqual(0)
    expect((box?.x ?? 0) + (box?.width ?? width)).toBeLessThanOrEqual(width + 1)
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
    expect(await page.evaluate(() => window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 1)).toBe(true)
  })
}
