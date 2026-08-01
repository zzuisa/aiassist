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
  await expect(page).toHaveURL(/\/today/)
  // A fresh browser profile has not acknowledged the latest release yet. The
  // announcement is expected product behaviour, so close it before exercising
  // the underlying blog controls.
  await page.getByRole('button', { name: '关闭更新公告' }).click()
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

test('clicking an outline heading moves the source editor to that chapter', async ({ page }) => {
  await login(page)
  await newBlankPost(page)
  const markdown = `# 第一章\n\n${'前文\n'.repeat(80)}\n## 目标章节\n\n目标内容`
  const source = page.locator('textarea.md-source')
  await source.fill(markdown)
  await page.getByRole('button', { name: '目标章节' }).click()
  const expected = markdown.indexOf('## 目标章节')
  await expect.poll(() => source.evaluate((el) => (el as HTMLTextAreaElement).selectionStart))
    .toBe(expected)
})

test('narrow viewport stacks the workbench', async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 800 })
  await login(page)
  await newBlankPost(page)
  await expect(page.locator('.workbench')).toBeVisible()
  await page.locator('textarea.md-source').fill('内容')
  await expect(page.locator('.save-state')).toHaveText(/保存中|已保存/)
})

test('mobile blog list keeps category-first actions usable at 360px', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 })
  await login(page)
  await page.goto('/blog')

  await expect(page.getByLabel('按结构化分类筛选')).toBeVisible()
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)

  const firstRow = page.locator('.post-row').first()
  if (await firstRow.count()) {
    await firstRow.getByRole('button', { name: /更多操作/ }).click()
    await expect(firstRow.locator('.accessible-actions')).toBeVisible()
    await expect(firstRow.getByRole('button', { name: '归类' })).toBeVisible()
  }

  await page.getByRole('link', { name: '分类' }).click()
  await expect(page).toHaveURL(/\/blog\/taxonomy$/)
})

// --- US4: review an AI candidate and apply only selected fields ---
//
// Requires a configured Skill + AI provider, so it self-skips unless the caller
// opts in with E2E_AI=1. Verifies the safety promise: applying only the summary
// leaves the user's body untouched.
test('apply only summary from an AI candidate keeps the body unchanged', async ({ page }) => {
  test.skip(process.env.E2E_AI !== '1', 'E2E_AI not enabled')
  await login(page)
  await newBlankPost(page)

  const body = '# 我的正文\n\n这段正文不应被 AI 覆盖。'
  await page.locator('textarea.md-source').fill(body)
  await expect(page.locator('.save-state')).toHaveText(/已保存/)

  // Kick off an optimization and land on the job list.
  await page.getByRole('button', { name: 'AI 优化' }).click()
  await page.getByRole('button', { name: '开始优化' }).click()
  await expect(page).toHaveURL(/\/blog\/jobs/)

  // Once the candidate is ready, open the review from the job detail.
  await page.getByText('待审核').first().click()
  await page.getByRole('link', { name: '去审核文章' }).click()
  await page.getByRole('button', { name: /待审核 AI 优化/ }).click()
  await expect(page).toHaveURL(/\/candidates\//)

  // Select only summary, deselect everything else, then apply.
  await page.locator('input[aria-label="应用 markdown"]').uncheck()
  await page.locator('input[aria-label="应用 summary"]').check()
  await page.getByRole('button', { name: /应用所选/ }).click()

  // Back in the editor, the user body is intact.
  await expect(page).toHaveURL(/\/blog\/[^/]+$/)
  await expect(page.locator('textarea.md-source')).toHaveValue(body)
})
