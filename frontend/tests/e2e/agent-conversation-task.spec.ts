import { expect, test } from '@playwright/test'

test('conversation task flow keeps writes behind an explicit confirmation action', async ({ page }) => {
  await page.goto('/agent')
  await expect(page.getByRole('heading', { name: '自助 Agent' })).toBeVisible()
  const composer = page.getByLabel('跟我说点什么')
  await composer.fill('嗨，帮我找最近十篇文章')
  await composer.press('Enter')
  await expect(page.getByRole('log')).toContainText('嗨，帮我找最近十篇文章')
  // Full backend-backed execution is covered by the integration suite. The E2E
  // invariant is that chat text itself never exposes an implicit approve action.
  await expect(page.getByRole('button', { name: /确认写入|批准/ })).toHaveCount(0)
})
