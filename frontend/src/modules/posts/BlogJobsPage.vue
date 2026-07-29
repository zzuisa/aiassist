<script setup lang="ts">
// Blog Job list (spec 005, US3, T079).
//
// Lists blog background jobs (capture / optimize / wordcloud) with an SSE-backed
// live status. The store is fed by a single EventSource; here we just read
// `blogJobs` and render display statuses. A `focus` query param highlights the
// job just submitted from the editor.
import { computed, onMounted } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useJobsStore } from '@/stores/jobs'
import { jobDisplay, jobTypeLabel } from '@/modules/posts/blogJobStatus'

const store = useJobsStore()
const route = useRoute()

const focusId = computed(() => (route.query.focus as string) || null)
const jobs = computed(() => store.blogJobs)

onMounted(() => {
  // Ensure we have a baseline even before the first SSE frame lands.
  store.connect()
  void store.refreshFromRest()
})
</script>

<template>
  <section class="blog-jobs">
    <header class="head">
      <h1>AI 任务</h1>
      <span
        class="conn"
        :data-connected="store.connected"
      >{{ store.connected ? '实时' : '离线' }}</span>
    </header>

    <p
      v-if="jobs.length === 0"
      class="empty"
    >
      暂无 AI 任务。在文章编辑页点击「AI 优化」即可创建。
    </p>

    <ul
      v-else
      class="job-list"
    >
      <li
        v-for="job in jobs"
        :key="job.id"
        class="job-row"
        :class="{ focused: job.id === focusId }"
      >
        <RouterLink
          class="job-link"
          :to="{ name: 'blog-job-detail', params: { id: job.id } }"
        >
          <span class="job-type">{{ jobTypeLabel(job.job_type) }}</span>
          <span
            class="badge"
            :data-tone="jobDisplay(job).tone"
          >{{ jobDisplay(job).label }}</span>
          <span
            v-if="['pending', 'queued', 'processing'].includes(job.status)"
            class="progress"
          >{{ job.progress }}%</span>
        </RouterLink>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.blog-jobs {
  padding: var(--space-4);
  max-width: 720px;
  margin: 0 auto;
}
.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.head h1 {
  font-size: 1.2rem;
  margin: 0;
}
.conn {
  font-size: 0.8rem;
  color: var(--color-text-muted);
}
.conn[data-connected='true'] {
  color: var(--status-done, #16a34a);
}
.empty {
  color: var(--color-text-muted);
  margin-top: var(--space-4);
}
.job-list {
  list-style: none;
  padding: 0;
  margin: var(--space-3) 0 0;
}
.job-row {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-2);
}
.job-row.focused {
  border-color: var(--status-normal);
  box-shadow: 0 0 0 2px var(--status-normal-soft, rgba(37, 99, 235, 0.2));
}
.job-link {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  text-decoration: none;
  color: inherit;
}
.job-type {
  font-weight: 600;
  flex: 1;
}
.progress {
  font-size: 0.85rem;
  color: var(--color-text-muted);
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
</style>
