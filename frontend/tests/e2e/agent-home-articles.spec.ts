import { expect, test } from '@playwright/test'

test('Agent starts as a fresh conversation instead of restoring historical chat', async ({ page }) => {
  await page.goto('/agent')

  await expect(page.getByRole('heading', { name: '自助 Agent' })).toBeVisible()
  await expect(page.getByRole('log')).toContainText('开始一次新对话')
  await expect(page.getByRole('log')).not.toContainText('正在加载会话')
})
