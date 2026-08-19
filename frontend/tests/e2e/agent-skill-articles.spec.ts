import { expect, test } from '@playwright/test'

test('article query accepts a Skill default and an explicit quantity without mandatory clarification', async ({
  page,
}) => {
  await page.goto('/agent')
  await expect(page.getByRole('heading', { name: '自助 Agent' })).toBeVisible()
  const composer = page.getByLabel('跟我说点什么')

  await composer.fill('查一下最近文章')
  await composer.press('Enter')
  await expect(page.getByRole('log')).toContainText('查一下最近文章')
  await expect(page.getByRole('log')).not.toContainText('需要查看最近多少篇文章')

  await composer.fill('查一下最近 3 篇文章')
  await composer.press('Enter')
  await expect(page.getByRole('log')).toContainText('查一下最近 3 篇文章')
  await expect(page.getByRole('log')).not.toContainText('缺少必要的数量条件')
})
