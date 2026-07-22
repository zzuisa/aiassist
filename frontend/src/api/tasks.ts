import { api } from '@/api/client'

export interface Task {
  id: string
  type: string
  title: string
  description?: string | null
  status: 'todo' | 'in_progress' | 'completed' | 'cancelled'
  priority: number
  importance: number
  start_at?: string | null
  due_at?: string | null
  estimated_minutes?: number | null
  actual_minutes?: number | null
  is_fixed: boolean
  is_ai_adjustable: boolean
  is_splittable: boolean
  tag_ids: string[]
  version: number
  completed_at?: string | null
  created_at: string
  updated_at: string
}

export interface TaskCreate {
  type?: string
  title: string
  description?: string | null
  priority?: number
  importance?: number
  start_at?: string | null
  due_at?: string | null
  is_fixed?: boolean
}

export interface TaskPage {
  items: Task[]
  next_cursor?: string | null
}

export interface TodayDashboard {
  date: string
  stats: Record<string, number>
  current_task: Task | null
  timeline: Task[]
  todos: Task[]
  habits: unknown[]
  overdue: Task[]
  conflicts: unknown[]
  suggestions: unknown[]
  recent_captures: unknown[]
  jobs: unknown[]
}

export const tasksApi = {
  list: (query?: Record<string, string>) => api.get<TaskPage>('/tasks', query),
  create: (body: TaskCreate) => api.post<Task>('/tasks', { type: 'task', ...body }),
  get: (id: string) => api.get<Task>(`/tasks/${id}`),
  patch: (id: string, body: Record<string, unknown>) => api.patch<Task>(`/tasks/${id}`, body),
  complete: (id: string, version: number, actualMinutes?: number) =>
    api.post<Task>(`/tasks/${id}/complete`, { version, actual_minutes: actualMinutes }),
  remove: (id: string) => api.del<void>(`/tasks/${id}`),
  today: (date?: string) => api.get<TodayDashboard>('/today', date ? { date } : undefined),
}
