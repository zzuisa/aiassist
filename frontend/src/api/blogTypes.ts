// Hand-maintained blog API types, mirroring
// specs/005-blog-content-management/contracts/openapi.yaml. Foundational surface
// for the blog content-management module; later user-story tasks extend it.
// Exported through ./types so callers keep importing from a single module.

// --- Enumerations (data-model.md §Post) ---------------------------------------

export type ContentStatus =
  | 'pending_capture'
  | 'pending_parse'
  | 'triage'
  | 'draft'
  | 'ai_queued'
  | 'ai_processing'
  | 'ai_review'
  | 'merge_required'
  | 'completed'
  | 'archived'
  | 'discarded'

export type ContentClass =
  | 'technical'
  | 'project'
  | 'learning'
  | 'life'
  | 'travel'
  | 'diary'
  | 'essay'
  | 'bookmark'
  | 'media'
  | 'item'
  | 'quick'

export type RevisionSource =
  | 'capture'
  | 'user_edit'
  | 'ai_candidate'
  | 'ai_applied'
  | 'restore'
  | 'import'
  | 'merge'

export type PostSourceStatus = 'pending' | 'extracting' | 'ready' | 'failed'

export type CandidateStatus =
  | 'pending'
  | 'applied'
  | 'rejected'
  | 'copied'
  | 'merge_required'

export type SkillScopeType = 'global' | 'content_class' | 'content_type'

// --- Core resources -----------------------------------------------------------

export interface Post {
  id: string
  title: string
  subtitle?: string | null
  summary?: string | null
  markdown: string
  status: string // publication status (existing posts semantics, unchanged)
  content_status: ContentStatus
  content_class: string
  content_type_id?: string | null
  language: string
  structured_data: Record<string, unknown>
  version: number
  current_revision_id: string
  created_at: string
  updated_at: string
}

export interface PostSource {
  id: string
  post_id: string
  kind: string // clipboard | url | quick | blank
  url?: string | null
  status: PostSourceStatus
  created_at: string
}

export interface PostRevision {
  id: string
  post_id: string
  source: RevisionSource
  version: number
  created_at: string
}

export interface ContentType {
  id: string
  content_class: string
  name: string
  schema_version: number
  enabled: boolean
}

export interface Skill {
  id: string
  name: string
  enabled: boolean
  current_version_id: string | null
  created_at: string
  updated_at: string
}

export interface SkillVersion {
  id: string
  skill_id: string
  version_number: number
  created_at: string
}

export interface AiCandidate {
  id: string
  post_id: string
  ai_run_id: string
  candidate_revision_id: string
  status: CandidateStatus
  created_at: string
}

export interface BlogSettings {
  schema_version: number
  create: Record<string, unknown>
  clipboard: Record<string, unknown>
  url_capture: Record<string, unknown>
  ai_apply: Record<string, unknown>
  word_cloud: Record<string, unknown>
}
