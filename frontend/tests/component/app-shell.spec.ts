import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('vue-router', () => ({
  RouterLink: {
    props: ['to'],
    template: '<a :href="to"><slot /></a>',
  },
  RouterView: { template: '<div class="router-view-stub" />' },
  useRoute: () => ({ path: '/today' }),
}))

vi.mock('@/stores/jobs', () => ({
  useJobsStore: () => ({
    activeJobs: [],
    reconnecting: false,
    unreadCount: 0,
    connect: vi.fn(),
    disconnect: vi.fn(),
  }),
}))

vi.mock('@/api/releases', () => ({
  releasesApi: { history: vi.fn() },
}))

vi.mock('@/components/jobs/TaskCenterDrawer.vue', () => ({
  default: { template: '<div class="task-center-stub" />' },
}))
vi.mock('@/components/notifications/NotificationCenter.vue', () => ({
  default: { template: '<div class="notification-center-stub" />' },
}))

import AppShell from '@/app/AppShell.vue'
import { releasesApi } from '@/api/releases'

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

describe('AppShell mobile navigation', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    vi.mocked(releasesApi.history).mockResolvedValue({ releases: [release] } as never)
  })

  it('exposes every primary route through the bottom navigation', () => {
    const wrapper = mount(AppShell, {
      global: {
        stubs: {
          RouterLink: {
            props: ['to'],
            template: '<a :href="to"><slot /></a>',
          },
          RouterView: { template: '<div class="router-view-stub" />' },
        },
      },
    })
    const nav = wrapper.find('.bottom-nav')

    expect(nav.attributes('aria-label')).toBe('主导航')
    expect(nav.findAll('.bottom-item')).toHaveLength(9)
    expect(nav.text()).toContain('今日')
    expect(nav.text()).toContain('博客')
    expect(nav.text()).toContain('AI 助手')
    expect(nav.text()).toContain('自助 Agent')
    expect(nav.text()).toContain('设置')
  })

  it('shows the update dialog once for an unseen release and links to history', async () => {
    const wrapper = mount(AppShell, {
      global: {
        stubs: {
          RouterLink: {
            props: ['to'],
            template: '<a :href="to"><slot /></a>',
          },
          RouterView: { template: '<div class="router-view-stub" />' },
        },
      },
    })
    await flushPromises()

    expect(wrapper.find('[role="dialog"]').text()).toContain('本次更新内容')
    expect(wrapper.find('a[href="/settings/updates"]').text()).toContain('查看更新历史')
    await wrapper.find('.secondary').trigger('click')
    expect(window.localStorage.getItem('aiassist:last-seen-release')).toBe(release.id)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })
})
