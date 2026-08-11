import { expect, test } from '@playwright/test'

test('conversation history remains visible after reload', async ({ page }) => {
  await page.goto('/agent')
  await expect(page.getByRole('log')).toBeVisible()
  await page.reload()
  await expect(page.getByRole('log')).toBeVisible()
})
