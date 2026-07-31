import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('@/api/releases', () => ({
  releasesApi: { history: vi.fn() },
}))

import { releasesApi } from '@/api/releases'
import ReleaseHistoryPage from '@/modules/releases/ReleaseHistoryPage.vue'

const release = {
  id: '2026.07.31.120000-a1b2c3d',
  version: '2026.07.31.120000',
  commit: 'a1b2c3d4',
  commit_short: 'a1b2c3d',
  message: 'feat: improve mobile blog flow',
  changes: ['前端界面与交互更新'],
  changed_files: ['frontend/src/app/AppShell.vue'],
  deployed_at: '2026-07-31T12:00:00Z',
  environment: 'production',
  git_pushed: true,
  deployment_status: 'verified',
  migration_head: null,
}

describe('ReleaseHistoryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(releasesApi.history).mockResolvedValue({ releases: [release] } as never)
  })

  it('shows current status, push status and changed files', async () => {
    const wrapper = mount(ReleaseHistoryPage)
    await flushPromises()

    expect(wrapper.text()).toContain('当前运行')
    expect(wrapper.text()).toContain('推送 已完成')
    expect(wrapper.text()).toContain('a1b2c3d')
    expect(wrapper.text()).toContain('frontend/src/app/AppShell.vue')
  })
})
