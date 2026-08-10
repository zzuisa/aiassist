import { api } from '@/api/client'

export interface CreateDefaultsSettings {
  content_class: string
  language: string
  content_type_id: string | null
  category_id: string | null
  tag_ids: string[]
  status: string
  editor_mode: string
  ai_enabled: boolean
  default_skill_id: string | null
  model: string | null
  generate_summary: boolean
  generate_keywords: boolean
  recommend_tags: boolean
  retain_original: boolean
}

export interface ClipboardSettings {
  enabled: boolean
  auto_parse: boolean
  default_content_class: string
  cleanup_format: boolean
  retain_original: boolean
  detect_urls: boolean
  auto_ai: boolean
  default_skill_id: string | null
}

export interface UrlCaptureSettings {
  enabled: boolean
  auto_fetch_title: boolean
  auto_extract_body: boolean
  default_content_class: string
  retain_original: boolean
  retain_snapshot: boolean
  extract_images: boolean
  auto_ai: boolean
  default_skill_id: string | null
}

export interface AiApplySettings {
  confirm_before_apply: boolean
  default_fields: string[]
  show_diff: boolean
  default_provider: 'radio' | 'aiassist'
  allow_auto_apply: boolean
  auto_apply_fields: string[]
  confirm_fields: string[]
  merge_on_version_change: boolean
  retain_job_history: boolean
}

export interface WordCloudSettings {
  enabled: boolean
  min_term_count: number
  max_terms: number
  exclude_terms: string[]
  excluded_content_classes: string[]
}

export interface BlogSettings {
  schema_version: 'blog-settings.v1'
  create_defaults: CreateDefaultsSettings
  clipboard: ClipboardSettings
  url_capture: UrlCaptureSettings
  ai_apply: AiApplySettings
  word_cloud: WordCloudSettings
  version: number
  warnings: string[]
}

export const blogSettingsApi = {
  get: () => api.get<BlogSettings>('/blog/settings'),
  update: (settings: BlogSettings) => {
    const body: Partial<BlogSettings> = { ...settings }
    delete body.warnings
    return api.put<BlogSettings>('/blog/settings', body)
  },
}
