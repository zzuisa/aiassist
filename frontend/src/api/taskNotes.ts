import { api, getCsrfToken } from '@/api/client'

export interface NoteAsset {
  id: string
  filename: string
  media_type: string
  width: number | null
  height: number | null
  position: number
  processing_status: string
}

export interface TaskNote {
  content: string
  version: number
  assets: NoteAsset[]
}

export interface AttachResult {
  upload_id: string
  status: 'attached' | 'failed'
  asset_id?: string
  error?: string
}

export const taskNotesApi = {
  get: (taskId: string) => api.get<TaskNote>(`/tasks/${taskId}/note`),
  save: (taskId: string, content: string, version?: number) =>
    api.put<TaskNote>(`/tasks/${taskId}/note`, { content, version }),
  attach: (taskId: string, uploadIds: string[]) =>
    api.post<{ note: TaskNote; results: AttachResult[] }>(`/tasks/${taskId}/note/assets`, {
      upload_ids: uploadIds,
    }),
  access: (taskId: string, assetId: string) =>
    api.get<{ url: string; expires_at: string }>(
      `/tasks/${taskId}/note/assets/${assetId}/access`,
    ),
}

interface UploadSession {
  id: string
}

/** Upload one image via the upload-session flow and return its completed id. */
export async function uploadNoteImage(file: File): Promise<string> {
  const session = await api.post<UploadSession>('/uploads', {
    purpose: 'task_note_image',
    filename: file.name,
    media_type: file.type,
    byte_size: file.size,
  })
  const csrf = getCsrfToken()
  const resp = await fetch(`/api/v1/uploads/${session.id}/content`, {
    method: 'PUT',
    headers: csrf ? { 'X-CSRF-Token': csrf } : {},
    body: file,
    credentials: 'same-origin',
  })
  if (!resp.ok) throw new Error(`upload failed: ${resp.status}`)
  await api.post(`/uploads/${session.id}/complete`)
  return session.id
}
