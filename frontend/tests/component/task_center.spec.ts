import { beforeEach, describe, expect, it } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import TaskCenterDrawer from '@/components/jobs/TaskCenterDrawer.vue'
import NotificationCenter from '@/components/notifications/NotificationCenter.vue'
import { useJobsStore } from '@/stores/jobs'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('TaskCenterDrawer', () => {
  it('groups active, waiting and failed jobs', () => {
    const jobs = useJobsStore()
    jobs.applyJobEvent({ job_id: 'a', job_version: 1, status: 'processing', progress: 40, current_step: '生成预览图' })
    jobs.applyJobEvent({ job_id: 'w', job_version: 1, status: 'waiting_user', progress: 100, current_step: '请确认' })
    jobs.applyJobEvent({
      job_id: 'f',
      job_version: 1,
      status: 'failed',
      progress: 50,
      error: { code: 'TIMEOUT', message: '内容已保存，可稍后重试', retryable: true },
    })
    const wrapper = mount(TaskCenterDrawer, { props: { open: true } })
    expect(wrapper.text()).toContain('进行中')
    expect(wrapper.text()).toContain('生成预览图')
    expect(wrapper.text()).toContain('等待确认')
    expect(wrapper.text()).toContain('失败')
    expect(wrapper.text()).toContain('内容已保存，可稍后重试')
  })

  it('shows a business-language job name, percent and progress bar', () => {
    const jobs = useJobsStore()
    jobs.applyJobEvent({
      job_id: 'a',
      job_version: 1,
      job_type: 'voice.transcribe',
      status: 'processing',
      progress: 65,
      current_step: '正在识别',
      created_at: '2026-07-24T10:00:00Z',
      started_at: '2026-07-24T10:00:01Z',
    })
    const wrapper = mount(TaskCenterDrawer, { props: { open: true } })
    expect(wrapper.text()).toContain('语音识别') // friendly name, not 'voice.transcribe'
    expect(wrapper.text()).not.toContain('voice.transcribe')
    expect(wrapper.text()).toContain('65%')
    expect(wrapper.find('.bar span').attributes('style')).toContain('65%')
    expect(wrapper.text()).toContain('开始')
  })

  it('shows failure reason, finish time and retry count', () => {
    const jobs = useJobsStore()
    jobs.applyJobEvent({
      job_id: 'f',
      job_version: 1,
      job_type: 'capture.process',
      status: 'failed',
      progress: 50,
      retry_count: 2,
      created_at: '2026-07-24T10:00:00Z',
      finished_at: '2026-07-24T10:00:30Z',
      error: { code: 'X', message: '图片分析未完成', retryable: true },
    })
    const wrapper = mount(TaskCenterDrawer, { props: { open: true } })
    expect(wrapper.text()).toContain('图片处理')
    expect(wrapper.text()).toContain('图片分析未完成')
    expect(wrapper.text()).toContain('结束')
    expect(wrapper.text()).toContain('已重试 2 次')
  })

  it('shows a retry button only for retryable failures', () => {
    const jobs = useJobsStore()
    jobs.applyJobEvent({
      job_id: 'f',
      job_version: 1,
      status: 'failed',
      error: { code: 'X', message: '失败', retryable: false },
    })
    const wrapper = mount(TaskCenterDrawer, { props: { open: true } })
    expect(wrapper.findAll('button').some((b) => b.text() === '重试')).toBe(false)
  })

  it('renders a reconnect banner without toasts', async () => {
    const jobs = useJobsStore()
    jobs.reconnecting = true
    const wrapper = mount(TaskCenterDrawer, { props: { open: true } })
    expect(wrapper.text()).toContain('正在重新连接')
  })

  it('exposes trace id only in a diagnostic detail', () => {
    const jobs = useJobsStore()
    jobs.applyJobEvent({
      job_id: 'f',
      job_version: 1,
      status: 'failed',
      trace_id: 'abc123',
      error: { code: 'X', message: '失败', retryable: true },
    })
    const wrapper = mount(TaskCenterDrawer, { props: { open: true } })
    expect(wrapper.find('details').exists()).toBe(true)
    expect(wrapper.text()).toContain('abc123')
  })
})

describe('NotificationCenter', () => {
  it('lists notifications and marks unread with a badge state', () => {
    const jobs = useJobsStore()
    jobs.applyNotification({ notification_id: 'n1', type: 'task_due', title: '联系房东', body: '30 分钟后到期', created_at: '' })
    const wrapper = mount(NotificationCenter, { props: { open: true } })
    expect(wrapper.text()).toContain('联系房东')
    expect(wrapper.find('li.unread').exists()).toBe(true)
  })
})
