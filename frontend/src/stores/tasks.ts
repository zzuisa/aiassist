import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ApiError } from '@/api/client'
import { tasksApi, type Task, type TaskCreate } from '@/api/tasks'

export const useTasksStore = defineStore('tasks', () => {
  const items = ref<Task[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  // A monotonic signal every view can watch to stay in sync: any task mutation
  // (here or elsewhere, e.g. a calendar drag) bumps it, so the Today list and the
  // calendar refetch and never drift apart.
  const changedAt = ref(0)

  function markChanged(): void {
    changedAt.value = Date.now()
  }

  async function load(status?: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const page = await tasksApi.list(status ? { status } : undefined)
      items.value = page.items
    } catch (err) {
      error.value = err instanceof ApiError ? err.message : '加载失败'
    } finally {
      loading.value = false
    }
  }

  async function create(body: TaskCreate): Promise<Task> {
    const task = await tasksApi.create(body)
    items.value = [task, ...items.value]
    markChanged()
    return task
  }

  async function complete(task: Task): Promise<void> {
    const updated = await tasksApi.complete(task.id, task.version)
    replace(updated)
    markChanged()
  }

  async function patch(id: string, body: Record<string, unknown>): Promise<Task> {
    const updated = await tasksApi.patch(id, body)
    replace(updated)
    markChanged()
    return updated
  }

  async function remove(id: string): Promise<void> {
    await tasksApi.remove(id)
    items.value = items.value.filter((t) => t.id !== id)
    markChanged()
  }

  function replace(task: Task): void {
    const idx = items.value.findIndex((t) => t.id === task.id)
    if (idx >= 0) items.value[idx] = task
    else items.value.unshift(task)
  }

  return {
    items,
    loading,
    error,
    changedAt,
    markChanged,
    load,
    create,
    complete,
    patch,
    remove,
    replace,
  }
})
