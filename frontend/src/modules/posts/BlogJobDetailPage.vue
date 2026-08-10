<script setup lang="ts">
// Blog Job detail (spec 005, US3, T079).
//
// Shows one blog job with a live, SSE-backed status (the store applies events),
// plus allowed retry/cancel actions and a link back to the article. When the AI
// run finishes with a reviewable candidate, it points to the article for review
// (the field-by-field apply flow lands in US4). No article content is shown here.
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api, ApiError } from '@/api/client'
import type { AsyncJob } from '@/api/types'
import { useJobsStore } from '@/stores/jobs'
import { jobDisplay, jobTypeLabel } from '@/modules/posts/blogJobStatus'

const store = useJobsStore()
const route = useRoute()
const jobId = computed(() => route.params.id as string)

const fetched = ref<AsyncJob | null>(null)
const busy = ref(false)
const actionNotice = ref('')
const actionFailure = ref('')

// Prefer the live store copy (SSE-updated); fall back to the one-shot fetch.
const job = computed<AsyncJob | null>(() => store.getJob(jobId.value) ?? fetched.value)

const display = computed(() => (job.value ? jobDisplay(job.value) : null))
const canCancel = computed(
  () =>
    !!job.value &&
    ['pending', 'queued', 'processing', 'waiting_user'].includes(job.value.status),
)
const canRetry = computed(
  () => !!job.value && job.value.status === 'failed' && job.value.error?.retryable !== false,
)
const postId = computed(() => (job.value?.entity?.type === 'post' ? job.value.entity.id : null))

function finishedJobNotice(status: string | undefined): string {
  if (status === 'completed') return '任务已完成，无需取消。'
  if (status === 'failed') return '任务已经失败，不能取消；你可以选择重试。'
  if (status === 'cancelled') return '任务已经取消。'
  return '任务已结束，无需取消。'
}

async function refresh(): Promise<void> {
  try {
    fetched.value = await api.get<AsyncJob>(`/jobs/${jobId.value}`)
  } catch {
    fetched.value = null
  }
}

async function cancel(): Promise<void> {
  if (!job.value || busy.value) return
  busy.value = true
  actionNotice.value = ''
  actionFailure.value = ''
  try {
    fetched.value = await api.post<AsyncJob>(`/jobs/${jobId.value}/cancel`)
    actionNotice.value = '已取消任务。'
  } catch (err) {
    if (err instanceof ApiError && err.code === 'job_finished') {
      actionNotice.value = finishedJobNotice(err.problem.job_status ?? job.value.status)
      await refresh()
    } else {
      actionFailure.value = '取消任务失败，请稍后重试。'
    }
  } finally {
    busy.value = false
  }
}

async function retry(): Promise<void> {
  if (!job.value || busy.value) return
  busy.value = true
  try {
    fetched.value = await api.post<AsyncJob>(`/jobs/${jobId.value}/retry`)
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  store.connect()
  void refresh()
})
</script>

<template>
  <section class="job-detail">
    <RouterLink
      class="back"
      :to="{ name: 'blog-jobs' }"
    >
      ← 返回任务列表
    </RouterLink>

    <p
      v-if="!job"
      class="empty"
    >
      任务不存在或已被清理。
    </p>

    <template v-else>
      <header class="head">
        <h1>{{ jobTypeLabel(job.job_type) }}</h1>
        <span
          class="badge"
          :data-tone="display?.tone"
        >{{ display?.label }}</span>
      </header>

      <dl class="meta">
        <dt>进度</dt>
        <dd>{{ job.progress }}%</dd>
        <dt v-if="job.current_step">
          当前步骤
        </dt>
        <dd v-if="job.current_step">
          {{ job.current_step }}
        </dd>
        <dt>创建时间</dt>
        <dd>{{ job.created_at }}</dd>
        <dt v-if="job.finished_at">
          完成时间
        </dt>
        <dd v-if="job.finished_at">
          {{ job.finished_at }}
        </dd>
      </dl>

      <p
        v-if="job.error"
        class="job-error"
        role="alert"
      >
        {{ job.error.message || job.error.code }}
      </p>
      <p
        v-if="actionNotice"
        class="job-notice"
        role="status"
      >
        {{ actionNotice }}
      </p>
      <p
        v-if="actionFailure"
        class="job-error"
        role="alert"
      >
        {{ actionFailure }}
      </p>

      <div
        v-if="job.status === 'waiting_user' || job.status === 'completed'"
        class="review"
      >
        <p>优化已完成，生成了待审核的候选版本。</p>
        <RouterLink
          v-if="postId"
          class="primary"
          :to="{ name: 'blog-post-editor', params: { id: postId } }"
        >
          去审核文章
        </RouterLink>
      </div>

      <div class="actions">
        <button
          v-if="canCancel"
          type="button"
          class="ghost"
          :disabled="busy"
          @click="cancel"
        >
          取消任务
        </button>
        <button
          v-if="canRetry"
          type="button"
          class="primary"
          :disabled="busy"
          @click="retry"
        >
          重试
        </button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.job-detail {
  padding: var(--space-4);
  max-width: 720px;
  margin: 0 auto;
}
.back {
  display: inline-block;
  margin-bottom: var(--space-3);
  color: var(--color-text-muted);
  text-decoration: none;
}
.head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.head h1 {
  font-size: 1.2rem;
  margin: 0;
}
.meta {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.35rem var(--space-3);
  margin: var(--space-4) 0;
}
.meta dt {
  color: var(--color-text-muted);
  font-size: 0.85rem;
}
.meta dd {
  margin: 0;
}
.job-error {
  color: var(--status-danger, #dc2626);
  background: var(--status-danger-soft, #fee2e2);
  padding: var(--space-3);
  border-radius: var(--radius-sm);
}
.job-notice {
  color: var(--status-info, #1d4ed8);
  background: var(--status-info-soft, #dbeafe);
  padding: var(--space-3);
  border-radius: var(--radius-sm);
}
.review {
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-3);
}
.actions {
  display: flex;
  gap: var(--space-2);
}
.badge {
  font-size: 0.8rem;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  background: var(--color-surface-muted, #eee);
}
.badge[data-tone='queued'] {
  background: var(--status-normal-soft, #e0e7ff);
}
.badge[data-tone='processing'] {
  background: var(--status-warn-soft, #fef3c7);
}
.badge[data-tone='review'] {
  background: var(--status-info-soft, #dbeafe);
}
.badge[data-tone='done'] {
  background: var(--status-done-soft, #dcfce7);
}
.badge[data-tone='failed'] {
  background: var(--status-danger-soft, #fee2e2);
}
.primary,
.ghost {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-sm);
  cursor: pointer;
  text-decoration: none;
}
.primary {
  border: none;
  background: var(--status-normal);
  color: #fff;
}
.ghost {
  border: 1px solid var(--color-border);
  background: none;
  color: inherit;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
