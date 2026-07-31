<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { formatDuration } from '@/api/jobs'
import { useJobsStore } from '@/stores/jobs'
import { jobContext, jobDisplay, providerLabel } from '@/modules/posts/blogJobStatus'

const props = defineProps<{ postId: string }>()
const store = useJobsStore()
const nowTick = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

const optimizationJobs = computed(() => {
  void nowTick.value
  return store.blogJobs
    .filter((job) =>
      job.job_type === 'blog.optimize' &&
      (job.entity?.id === props.postId || jobContext(job).post_id === props.postId),
    )
    .slice(0, 6)
})
const visible = computed(() =>
  optimizationJobs.value.filter((job, index) =>
    ['pending', 'queued', 'processing', 'waiting_user'].includes(job.status) || index < 2,
  ),
)
const runningCount = computed(() =>
  optimizationJobs.value.filter((job) => ['pending', 'queued', 'processing'].includes(job.status)).length,
)

onMounted(() => {
  store.connect()
  void store.refreshFromRest()
  timer = setInterval(() => { nowTick.value += 1 }, 1000)
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <section
    v-if="visible.length"
    class="optimization-progress"
    aria-label="文章优化进度"
  >
    <header>
      <div>
        <strong>{{ runningCount ? `正在优化（${runningCount}）` : '最近的优化任务' }}</strong>
        <span class="live" :data-live="store.connected">{{ store.connected ? '实时更新' : '连接中…' }}</span>
      </div>
      <RouterLink :to="{ name: 'blog-jobs' }">查看全部任务</RouterLink>
    </header>

    <div class="task-grid">
      <RouterLink
        v-for="job in visible"
        :key="job.id"
        class="task-card"
        :to="{ name: 'blog-job-detail', params: { id: job.id } }"
      >
        <div class="task-head">
          <span class="provider">{{ providerLabel(job) ?? 'AI' }}</span>
          <span class="status" :data-tone="jobDisplay(job).tone">{{ jobDisplay(job).label }}</span>
          <b>{{ job.progress }}%</b>
        </div>
        <div
          class="bar"
          role="progressbar"
          :aria-valuenow="job.progress"
          aria-valuemin="0"
          aria-valuemax="100"
        ><span :style="{ width: `${job.progress}%` }" /></div>
        <div class="task-foot">
          <span>{{ job.current_step ?? '等待处理' }}</span>
          <span>{{ formatDuration(job.started_at ?? job.created_at, job.finished_at) }}</span>
        </div>
        <p v-if="job.error" class="error">{{ job.error.message }}</p>
      </RouterLink>
    </div>
  </section>
</template>

<style scoped>
.optimization-progress {
  margin: 0 var(--space-4) var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--status-ai, #7c3aed);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--status-ai, #7c3aed) 6%, var(--color-surface));
}
header, header > div, .task-head, .task-foot { display: flex; align-items: center; }
header { justify-content: space-between; gap: var(--space-3); }
header > div { gap: var(--space-2); }
header a { font-size: .82rem; }
.live { font-size: .75rem; color: var(--color-text-muted); }
.live[data-live='true'] { color: var(--status-done, #16a34a); }
.task-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: var(--space-2); margin-top: var(--space-2); }
.task-card { color: inherit; text-decoration: none; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: var(--space-2); }
.task-card:hover { border-color: var(--status-ai, #7c3aed); }
.task-head { gap: var(--space-2); }
.task-head b { margin-left: auto; font-size: .82rem; font-variant-numeric: tabular-nums; }
.provider, .status { font-size: .75rem; padding: .12rem .42rem; border-radius: 999px; background: var(--color-surface-2); }
.status[data-tone='processing'] { color: var(--status-ai, #7c3aed); }
.bar { height: 7px; overflow: hidden; border-radius: 999px; background: var(--color-surface-2); margin: var(--space-2) 0; }
.bar span { display: block; height: 100%; background: linear-gradient(90deg, var(--status-normal), var(--status-ai)); transition: width .35s ease; }
.task-foot { justify-content: space-between; gap: var(--space-2); color: var(--color-text-muted); font-size: .78rem; }
.error { margin: var(--space-1) 0 0; color: var(--status-urgent); font-size: .78rem; }
@media (prefers-reduced-motion: reduce) { .bar span { transition: none; } }
</style>
