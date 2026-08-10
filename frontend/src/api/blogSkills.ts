// Blog Skill management API client (spec 005, US5, T105).
//
// Skills are versioned AI-behaviour configs; versions are immutable, editing
// appends a new version. Deterministic defaults (global/content_class/
// content_type) decide which skill an optimization resolves to.

import { api } from '@/api/client'
import type { AsyncJob } from '@/api/types'

export type LongContentStrategy = 'reject' | 'chunk' | 'summarize_then_process'

export type FieldPolicy =
  | 'forbid'
  | 'suggest_only'
  | 'require_confirmation'
  | 'fill_if_empty'
  | 'auto_fill'
  | 'allow_overwrite'
  | 'keep_both_on_conflict'

// blog-skill-config.v1 (mirrors BlogSkillConfigV1).
export interface SkillConfig {
  schema_version: 'blog-skill-config.v1'
  applicable_content_classes: string[]
  applicable_content_type_ids: string[]
  processing_goal: string
  content_rules: string[]
  title_rules: string[]
  summary_rules: string[]
  body_structure: string[]
  taxonomy_rules: string[]
  keyword_rules: string[]
  prohibitions: string[]
  field_policies: Record<string, FieldPolicy>
  output_fields: string[]
  output_schema: 'blog-optimization.v1'
  validation_rules: string[]
  recommended_model: string | null
  max_content_chars: number
  long_content_strategy: LongContentStrategy
}

export interface SkillVersion {
  id: string
  skill_id: string
  version_number: number
  schema_version: string
  recommended_model: string | null
  max_content_chars: number
  long_content_strategy: LongContentStrategy
  change_summary: string | null
  created_at: string
  config?: SkillConfig
}

export interface ScopeDefault {
  scope_type: 'global' | 'content_class' | 'content_type'
  scope_key: string
  skill_id: string
}

export interface Skill {
  id: string
  name: string
  description: string | null
  enabled: boolean
  current_version: SkillVersion | null
  current_version_complete: boolean
  default_scopes: Array<{ scope_type: string; scope_key: string }>
  created_at: string
  updated_at: string
}

export interface SkillCreateBody {
  name: string
  description?: string | null
  config?: SkillConfig
  recommended_model?: string | null
  max_content_chars?: number
  long_content_strategy?: LongContentStrategy
}

export interface SkillVersionBody {
  config: SkillConfig
  recommended_model?: string | null
  max_content_chars?: number
  long_content_strategy?: LongContentStrategy
  change_summary?: string | null
}

export interface SkillRunSummary {
  id: string
  post_id: string
  skill_version_id: string
  optimization_type: string
  outcome: string | null
  created_at: string
}

export interface SkillDryRunBody {
  title: string
  markdown: string
  instruction?: string | null
}

export const blogSkillsApi = {
  list: () => api.get<Skill[]>('/blog/skills'),
  get: (id: string) => api.get<Skill>(`/blog/skills/${id}`),
  create: (body: SkillCreateBody) => api.post<Skill>('/blog/skills', body),
  updateMeta: (id: string, body: { name?: string; description?: string | null }) =>
    api.patch<Skill>(`/blog/skills/${id}`, body),
  setEnabled: (id: string, enabled: boolean) =>
    api.post<Skill>(`/blog/skills/${id}/enabled`, { enabled }),
  remove: (id: string) => api.del<void>(`/blog/skills/${id}`),
  copy: (id: string) => api.post<Skill>(`/blog/skills/${id}/copy`),
  listVersions: (id: string) => api.get<SkillVersion[]>(`/blog/skills/${id}/versions`),
  addVersion: (id: string, body: SkillVersionBody) =>
    api.post<SkillVersion>(`/blog/skills/${id}/versions`, body),
  restoreVersion: (id: string, versionId: string) =>
    api.post<SkillVersion>(`/blog/skills/${id}/versions/${versionId}/restore`),
  recentRuns: (id: string) => api.get<SkillRunSummary[]>(`/blog/skills/${id}/runs`),
  dryRun: (id: string, body: SkillDryRunBody) =>
    api.post<AsyncJob>(`/blog/skills/${id}/dry-run`, body),
  getDryRunJob: (jobId: string) => api.get<AsyncJob>(`/jobs/${jobId}`),
  listDefaults: () => api.get<ScopeDefault[]>('/blog/skills/defaults/list'),
  setDefault: (body: ScopeDefault) => api.put<ScopeDefault>('/blog/skills/defaults', body),
  removeDefault: (scopeType: string, scopeKey: string) =>
    api.del<void>(`/blog/skills/defaults?scope_type=${scopeType}&scope_key=${scopeKey}`),
}
