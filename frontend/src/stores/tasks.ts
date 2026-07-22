import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ApiError } from '@/api/client'
import { tasksApi, type Task, type TaskCreate } from '@/api/tasks'

export const useTasksStore = defineStore('tasks', () => {
  const items = ref<Task[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

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
    return task
  }

  async function complete(task: Task): Promise<void> {
    const updated = await tasksApi.complete(task.id, task.version)
    replace(updated)
  }

  async function patch(id: string, body: Record<string, unknown>): Promise<Task> {
    const updated = await tasksApi.patch(id, body)
    replace(updated)
    return updated
  }

  async function remove(id: string): Promise<void> {
    await tasksApi.remove(id)
    items.value = items.value.filter((t) => t.id !== id)
  }

  function replace(task: Task): void {
    const idx = items.value.findIndex((t) => t.id === task.id)
    if (idx >= 0) items.value[idx] = task
    else items.value.unshift(task)
  }

  return { items, loading, error, load, create, complete, patch, remove, replace }
})
