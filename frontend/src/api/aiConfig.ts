import { api } from '@/api/client'

export interface AIConfigModule {
  key: string
  title: string
  allowed_tool_keys: string[]
  active_prompt_version_id: string | null
  active_skill_version_id: string | null
  safety_boundary: string
}

export interface AIVersion {
  id: string
  version_number: number
  instruction: string
  created_at: string
}

export interface AISkillVersion extends AIVersion {
  name: string
  parameter_defaults: Record<string, Record<string, unknown>>
  allowed_tool_keys?: string[]
}

export interface AIConfigModuleDetail extends AIConfigModule {
  baseline_instruction: string
  prompt_versions: AIVersion[]
  skill_versions: AISkillVersion[]
}

export interface AIConfigDryRunResult {
  module_key: string
  status: string
  route_kind?: string
  selected_tool?: string | null
  tool_call?: { name: string; arguments: Record<string, unknown> } | null
  arguments?: Record<string, unknown>
  validation_errors?: string[]
  message: string
}

export interface AIConfigBinding {
  id: string
  module_key: string
  prompt_version_id: string | null
  skill_version_id: string | null
  model_key: string
  run_reference: string | null
  created_at: string
}

export const aiConfigApi = {
  list: () => api.get<AIConfigModule[]>('/ai-config/modules'),
  get: (moduleKey: string) => api.get<AIConfigModuleDetail>(`/ai-config/modules/${moduleKey}`),
  createPrompt: (moduleKey: string, body: { instruction: string; change_summary?: string }) =>
    api.post<AIVersion>(`/ai-config/modules/${moduleKey}/prompt-versions`, body),
  createSkill: (
    moduleKey: string,
    body: { name: string; instruction: string; parameter_defaults: Record<string, Record<string, unknown>> },
  ) => api.post<AISkillVersion>(`/ai-config/modules/${moduleKey}/skill-versions`, body),
  activate: (
    moduleKey: string,
    body: { prompt_version_id?: string | null; skill_version_id?: string | null },
  ) => api.post<void>(`/ai-config/modules/${moduleKey}/activate`, body),
  dryRun: (moduleKey: string, inputText: string) =>
    api.post<AIConfigDryRunResult>(`/ai-config/modules/${moduleKey}/dry-run`, {
      input_text: inputText,
    }),
  listBindings: () => api.get<AIConfigBinding[]>('/ai-config/modules/bindings/recent'),
}
