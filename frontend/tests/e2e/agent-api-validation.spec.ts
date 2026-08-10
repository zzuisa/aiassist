import { expect, test, type APIResponse, type Page, type TestInfo } from '@playwright/test'

const EMAIL = process.env.E2E_EMAIL
const PASSWORD = process.env.E2E_PASSWORD

const TERMINAL_STATUSES = new Set([
  'success',
  'partial_success',
  'failed',
  'waiting_confirmation',
])

type LoginResponse = {
  csrf_token: string
  user: {
    id: string
    email: string
  }
}

type AgentTask = {
  task_id: string
  job_id: string
  intent_key: string
  status: string
  result_summary: string | null
}

type AgentRun = {
  agent_name: string
  agent_version: string
  status: string
  current_tool: string | null
  error_message: string | null
}

type AgentTaskDetail = AgentTask & {
  runs: AgentRun[]
}

type AgentStatusEvent = {
  task_id?: string
  job_id?: string
  agent?: {
    agent_name?: string
    status?: string
  }
}

type ValidationSummary = {
  target: string
  health: string
  unauthenticated_status: number
  authenticated_user_id: string
  task_id: string
  job_id: string
  intent_key: string
  final_status: string
  agent_runs: Array<{
    agent_name: string
    agent_version: string
    status: string
    current_tool: string | null
  }>
  sse_event_count: number
  duration_ms: number
}

test.skip(!EMAIL || !PASSWORD, 'E2E_EMAIL/E2E_PASSWORD not configured')
test.setTimeout(90_000)

async function json<T>(response: APIResponse): Promise<T> {
  return await response.json() as T
}

async function startAgentEventCollector(page: Page): Promise<void> {
  await page.evaluate(async () => {
    type ValidationWindow = Window & {
      __agentValidationEvents?: unknown[]
      __agentValidationSource?: EventSource
    }
    const validationWindow = window as ValidationWindow
    validationWindow.__agentValidationEvents = []
    await new Promise<void>((resolve, reject) => {
      const source = new EventSource('/api/v1/events/jobs')
      validationWindow.__agentValidationSource = source
      const timeoutId = window.setTimeout(() => {
        source.close()
        reject(new Error('Timed out while opening the job event stream'))
      }, 10_000)
      source.addEventListener('open', () => {
        window.clearTimeout(timeoutId)
        resolve()
      }, { once: true })
      source.addEventListener('agent.status_changed', (event) => {
        try {
          validationWindow.__agentValidationEvents?.push(JSON.parse((event as MessageEvent).data))
        } catch {
          // Invalid payloads are ignored here and will make the event assertion fail.
        }
      })
    })
  })
}

async function matchingEvents(page: Page, taskId: string): Promise<AgentStatusEvent[]> {
  return await page.evaluate((expectedTaskId) => {
    type ValidationWindow = Window & { __agentValidationEvents?: AgentStatusEvent[] }
    const events = (window as ValidationWindow).__agentValidationEvents ?? []
    return events.filter((event) => event.task_id === expectedTaskId)
  }, taskId)
}

async function stopAgentEventCollector(page: Page): Promise<void> {
  await page.evaluate(() => {
    type ValidationWindow = Window & { __agentValidationSource?: EventSource }
    const validationWindow = window as ValidationWindow
    validationWindow.__agentValidationSource?.close()
    delete validationWindow.__agentValidationSource
  })
}

async function renderSummary(page: Page, summary: ValidationSummary, testInfo: TestInfo): Promise<void> {
  await page.setContent(`
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Agent API 一键验收</title>
        <style>
          :root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; }
          body { margin: 0; background: #07111f; color: #e5eefb; }
          main { width: min(980px, calc(100% - 32px)); margin: 32px auto; }
          h1 { margin: 0 0 8px; font-size: 30px; }
          .subtitle { margin: 0 0 24px; color: #9fb2ca; }
          .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
          .card { padding: 16px; border: 1px solid #263d57; border-radius: 14px; background: #0d1c2d; }
          .label { color: #8fa6c0; font-size: 13px; }
          .value { margin-top: 7px; font-size: 18px; overflow-wrap: anywhere; }
          .ok { color: #61d095; }
          pre { margin-top: 16px; padding: 18px; border-radius: 14px; background: #091624;
                border: 1px solid #263d57; white-space: pre-wrap; overflow-wrap: anywhere; }
        </style>
      </head>
      <body>
        <main>
          <h1>Agent API 一键验收</h1>
          <p class="subtitle">健康、鉴权、异步任务、SSE 与终态检查已完成</p>
          <section class="grid">
            <article class="card"><div class="label">最终状态</div><div id="status" class="value ok"></div></article>
            <article class="card"><div class="label">运行 Agent</div><div id="runs" class="value"></div></article>
            <article class="card"><div class="label">SSE 事件</div><div id="events" class="value"></div></article>
            <article class="card"><div class="label">总耗时</div><div id="duration" class="value"></div></article>
          </section>
          <pre id="summary" aria-label="脱敏验收摘要"></pre>
        </main>
      </body>
    </html>
  `)
  await page.locator('#status').evaluate((element, value) => { element.textContent = value }, summary.final_status)
  await page.locator('#runs').evaluate((element, value) => { element.textContent = value }, String(summary.agent_runs.length))
  await page.locator('#events').evaluate((element, value) => { element.textContent = value }, String(summary.sse_event_count))
  await page.locator('#duration').evaluate((element, value) => { element.textContent = `${value} ms` }, summary.duration_ms)
  await page.locator('#summary').evaluate((element, value) => {
    element.textContent = JSON.stringify(value, null, 2)
  }, summary)

  await testInfo.attach('agent-validation-summary.json', {
    body: Buffer.from(JSON.stringify(summary, null, 2)),
    contentType: 'application/json',
  })
  await testInfo.attach('agent-validation-dashboard.png', {
    body: await page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  })
}

test('一键验证 Agent API 只读任务全流程', async ({ page, context }, testInfo) => {
  const startedAt = Date.now()
  let healthStatus = ''
  let unauthenticatedStatus = 0
  let login: LoginResponse | null = null
  let created: AgentTask | null = null
  let detail: AgentTaskDetail | null = null
  let events: AgentStatusEvent[] = []

  await test.step('1. 检查后端就绪状态', async () => {
    const response = await context.request.get('/health/ready')
    expect(response.status()).toBe(200)
    const payload = await json<{ status: string }>(response)
    expect(payload.status).toBe('ready')
    healthStatus = payload.status
  })

  await test.step('2. 验证未登录请求被拒绝', async () => {
    const response = await context.request.get('/api/v1/agent/tasks')
    unauthenticatedStatus = response.status()
    expect(unauthenticatedStatus).toBe(401)
  })

  await test.step('3. 建立同源 Cookie 与 CSRF 会话', async () => {
    const response = await context.request.post('/api/v1/auth/login', {
      data: { email: EMAIL!, password: PASSWORD! },
    })
    expect(response.status()).toBe(200)
    login = await json<LoginResponse>(response)
    expect(login.csrf_token).not.toHaveLength(0)
    expect(login.user.id).not.toHaveLength(0)
    await page.goto('/today')
  })

  await test.step('4. 打开既有 SSE 状态通道', async () => {
    await startAgentEventCollector(page)
  })

  await test.step('5. 创建只读 Agent 查询任务', async () => {
    const response = await context.request.post('/api/v1/agent/tasks', {
      headers: { 'X-CSRF-Token': login!.csrf_token },
      data: { request_text: '给我最近 10 篇文章' },
    })
    expect(response.status()).toBe(202)
    created = await json<AgentTask>(response)
    expect(created.intent_key).toBe('articles.list_recent')
    expect(created.status).toBe('pending')
  })

  await test.step('6. 等待 Agent 状态事件与任务终态', async () => {
    await expect.poll(async () => {
      events = await matchingEvents(page, created!.task_id)
      return events.length
    }, { intervals: [250, 500, 1_000], timeout: 15_000 }).toBeGreaterThan(0)

    await expect.poll(async () => {
      const response = await context.request.get(`/api/v1/agent/tasks/${created!.task_id}`)
      expect(response.status()).toBe(200)
      detail = await json<AgentTaskDetail>(response)
      return TERMINAL_STATUSES.has(detail.status)
    }, { intervals: [250, 500, 1_000, 2_000], timeout: 45_000 }).toBe(true)
    expect(detail!.status).toBe('success')
    expect(detail!.runs).toHaveLength(1)
    expect(detail!.runs[0]?.status).toBe('success')
  })

  await test.step('7. 校验最小数据结果并生成脱敏报告', async () => {
    expect(detail!.result_summary).not.toBeNull()
    const result = JSON.parse(detail!.result_summary!) as Record<string, unknown>
    expect(result).toHaveProperty('处理结果')
    expect(JSON.stringify(result)).not.toContain('content_md')
    expect(JSON.stringify(result)).not.toContain('content_html')

    events = await matchingEvents(page, created!.task_id)
    const summary: ValidationSummary = {
      target: testInfo.project.use.baseURL ?? '',
      health: healthStatus,
      unauthenticated_status: unauthenticatedStatus,
      authenticated_user_id: login!.user.id,
      task_id: created!.task_id,
      job_id: created!.job_id,
      intent_key: created!.intent_key,
      final_status: detail!.status,
      agent_runs: detail!.runs.map((run) => ({
        agent_name: run.agent_name,
        agent_version: run.agent_version,
        status: run.status,
        current_tool: run.current_tool,
      })),
      sse_event_count: events.length,
      duration_ms: Date.now() - startedAt,
    }
    await renderSummary(page, summary, testInfo)
  })

  await stopAgentEventCollector(page)
})
