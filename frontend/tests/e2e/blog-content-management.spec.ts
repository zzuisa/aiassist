import { test, expect, type Page } from '@playwright/test'

// US1 journey: capture durable content before any AI runs.
// Requires a running stack + seeded account; self-skips without env config so it
// is safe to keep in the default suite.
const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD

test.skip(!EMAIL || !PASSWORD, 'E2E_EMAIL/E2E_PASSWORD not configured')

async function login(page: Page): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('邮箱').fill(EMAIL!)
  await page.getByLabel('密码').fill(PASSWORD!)
  await page.getByRole('button', { name: '登录' }).click()
}

test('quick capture saves and returns to the list (happy path)', async ({ page }) => {
  await login(page)
  await page.goto('/blog')
  await page.getByRole('button', { name: '新建内容' }).click()

  // Source picker → quick record.
  await page.getByText('快速记录', { exact: true }).click()
  await page.locator('textarea').fill('端到端的快速记录内容')
  await page.getByRole('button', { name: '保存', exact: true }).click()

  // Toast confirms the durable save; the item shows up in the list.
  await expect(page.getByText('已保存到「待整理」')).toBeVisible()
})

test('url capture stays durable and reports async extraction', async ({ page }) => {
  await login(page)
  await page.goto('/blog')
  await page.getByRole('button', { name: '新建内容' }).click()
  await page.getByText('从网址', { exact: true }).click()

  await page.getByPlaceholder('https://…').fill('https://example.com/an-article')
  await page.getByRole('button', { name: '保存并抓取' }).click()

  // The record is saved before extraction completes.
  await expect(page.getByText('已保存，正在后台抓取正文…')).toBeVisible()
  // We are taken into the durable draft.
  await expect(page).toHaveURL(/\/blog\//)
})

test('url capture rejects an unsafe address (failure path)', async ({ page }) => {
  await login(page)
  await page.goto('/blog')
  await page.getByRole('button', { name: '新建内容' }).click()
  await page.getByText('从网址', { exact: true }).click()

  await page.getByPlaceholder('https://…').fill('http://169.254.169.254/latest/meta-data')
  await page.getByRole('button', { name: '保存并抓取' }).click()

  await expect(page.getByText('该链接不被允许（可能是内网地址或非法协议）。')).toBeVisible()
})

// --- US2: editing an article ---

async function newBlankPost(page: Page): Promise<void> {
  await page.goto('/blog')
  await page.getByRole('button', { name: '新建内容' }).click()
  await page.getByText('空白文章', { exact: true }).click()
  await expect(page).toHaveURL(/\/blog\/[0-9a-f-]+$/)
}

test('edit an article in source mode and see it autosave', async ({ page }) => {
  await login(page)
  await newBlankPost(page)

  await page.getByRole('button', { name: '源码' }).click()
  await page.locator('textarea.md-source').fill(
    '# 标题\n\n> 引用\n\n- 一\n- 二\n\n```js\nconst x = 1\n```',
  )
  // Autosave shows a visible state.
  await expect(page.locator('.save-state')).toHaveText(/保存中|已保存/)

  // Preview renders the supported blocks.
  await page.getByRole('button', { name: '预览' }).click()
  await expect(page.locator('.md-preview h1')).toHaveText('标题')
  await expect(page.locator('.md-preview blockquote')).toHaveText('引用')
  await expect(page.locator('.md-code')).toContainText('const x = 1')
})

test('focus mode hides the outline and sidebar', async ({ page }) => {
  await login(page)
  await newBlankPost(page)
  await page.locator('textarea.md-source').fill('# H\n\ntext')
  await expect(page.locator('.outline')).toBeVisible()
  await page.getByRole('button', { name: '专注' }).click()
  await expect(page.locator('.outline')).toBeHidden()
  await expect(page.locator('.sidebar')).toHaveCount(0)
})

test('narrow viewport stacks the workbench', async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 800 })
  await login(page)
  await newBlankPost(page)
  await expect(page.locator('.workbench')).toBeVisible()
  await page.locator('textarea.md-source').fill('内容')
  await expect(page.locator('.save-state')).toHaveText(/保存中|已保存/)
})
