<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { tasksApi, type Task, type TodayDashboard } from '@/api/tasks'
import { useTasksStore } from '@/stores/tasks'
import QuickTaskInput from '@/modules/tasks/QuickTaskInput.vue'
import TaskCard from '@/modules/tasks/TaskCard.vue'

const store = useTasksStore()
const dashboard = ref<TodayDashboard | null>(null)
const loading = ref(true)

async function refresh(): Promise<void> {
  dashboard.value = await tasksApi.today()
}

onMounted(async () => {
  try {
    await refresh()
  } finally {
    loading.value = false
  }
})

async function onCreate(title: string): Promise<void> {
  await store.create({ title })
  await refresh()
}

async function onComplete(task: Task): Promise<void> {
  await tasksApi.complete(task.id, task.version)
  await refresh()
}
</script>

<template>
  <main class="today">
    <header class="head">
      <h1>今日</h1>
      <span
        v-if="dashboard"
        class="date"
      >{{ dashboard.date }}</span>
    </header>

    <QuickTaskInput @create="onCreate" />

    <p
      v-if="loading"
      class="muted"
    >
      加载中…
    </p>

    <template v-else-if="dashboard">
      <section
        v-if="dashboard.current_task"
        class="current"
        aria-label="当前任务"
      >
        <h2>现在最该做</h2>
        <TaskCard
          :task="dashboard.current_task"
          @complete="onComplete"
          @open="() => {}"
        />
      </section>

      <section aria-label="待办">
        <h2>待办 ({{ dashboard.todos.length }})</h2>
        <p
          v-if="dashboard.todos.length === 0"
          class="muted"
        >
          今天还没有待办。
        </p>
        <div class="list">
          <TaskCard
            v-for="t in dashboard.todos"
            :key="t.id"
            :task="t"
            @complete="onComplete"
            @open="() => {}"
          />
        </div>
      </section>

      <section
        v-if="dashboard.overdue.length"
        aria-label="逾期"
      >
        <h2 class="overdue">
          逾期 ({{ dashboard.overdue.length }})
        </h2>
        <div class="list">
          <TaskCard
            v-for="t in dashboard.overdue"
            :key="t.id"
            :task="t"
            @complete="onComplete"
            @open="() => {}"
          />
        </div>
      </section>
    </template>
  </main>
</template>

<style scoped>
.today {
  padding: var(--space-4);
  padding-top: calc(var(--safe-top) + var(--space-4));
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  max-width: 720px;
  margin: 0 auto;
}
.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.date {
  color: var(--color-text-muted);
}
.list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.muted {
  color: var(--color-text-muted);
}
.overdue {
  color: var(--status-urgent);
}
h2 {
  font-size: 1rem;
  margin: 0 0 var(--space-2);
}
</style>
