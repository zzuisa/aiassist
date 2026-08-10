import { api } from '@/api/client'

export interface PlanTask {
  title: string
  local_date: string | null
  local_time: string | null
  important: boolean
  [k: string]: unknown
}

export interface PlanState {
  job_id: string
  status: string
  questions: string[]
  tasks: PlanTask[]
  summary: string
  created: number | null
}

export interface QA {
  question: string
  answer: string
}

export const planApi = {
  // Enqueue background analysis; returns immediately with the job id.
  create: (text: string) => api.post<{ job_id: string; status: string }>('/tasks/plan', { text }),
  get: (jobId: string) => api.get<PlanState>(`/tasks/plan/${jobId}`),
  answer: (jobId: string, answers: QA[]) =>
    api.post<{ job_id: string; status: string }>(`/tasks/plan/${jobId}/answer`, { answers }),
  skip: (jobId: string) => api.post<{ job_id: string; status: string }>(`/tasks/plan/${jobId}/skip`),
}
