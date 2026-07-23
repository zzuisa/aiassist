// Hand-maintained API types for the MVP. These mirror contracts/openapi.yaml;
// Phase 12 (T137) adds generated types + a drift check.

export interface User {
  id: string
  email: string
  display_name: string
  timezone: string
  locale: string
  notification_preferences?: Record<string, unknown>
}

export interface LoginResponse {
  user: User
  csrf_token: string
}

export type JobStatus =
  | 'pending'
  | 'queued'
  | 'processing'
  | 'waiting_user'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface EntityRef {
  type: string
  id: string
}

export interface JobError {
  code: string
  message: string
  retryable: boolean
}

export interface AsyncJob {
  id: string
  job_type: string
  entity?: EntityRef | null
  status: JobStatus
  priority: number
  progress: number
  current_step?: string | null
  result?: Record<string, unknown> | null
  error?: JobError | null
  retry_count: number
  trace_id?: string | null
  created_at: string
  started_at?: string | null
  updated_at: string
  finished_at?: string | null
}

export interface NotificationItem {
  id: string
  type: string
  title: string
  body: string
  status: 'unread' | 'read' | 'archived'
  entity?: EntityRef | null
  created_at: string
}
