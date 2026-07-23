import { api } from '@/api/client'

export interface VoiceCandidate {
  title: string
  content_type: 'task' | 'fixed_event' | 'reminder' | 'note'
  description: string | null
  local_date: string | null
  local_time: string | null
  timezone: string
  duration_minutes: number | null
  priority: number
  important: boolean
  reminder: { channel: 'in_app' | 'email'; offset_minutes: number } | null
  recurring: boolean
  recurrence_rule: string | null
  original_text: string
}

export interface VoiceRecord {
  id: string
  status:
    | 'uploaded'
    | 'transcribing'
    | 'parsing'
    | 'waiting_user'
    | 'confirmed'
    | 'discarded'
    | 'failed'
  transcript: string | null
  candidate: VoiceCandidate | null
  schema_version: string | null
  job_id: string | null
  error: { code: string; message: string } | null
  created_at: string
}

export interface UploadSession {
  id: string
  status: string
  upload_url: string
  expires_at: string
}

export const voiceApi = {
  createUpload: (filename: string, mediaType: string, byteSize: number) =>
    api.post<UploadSession>('/uploads', {
      purpose: 'voice',
      filename,
      media_type: mediaType,
      byte_size: byteSize,
    }),
  completeUpload: (uploadId: string) => api.post<UploadSession>(`/uploads/${uploadId}/complete`),
  create: (uploadId: string) => api.post<VoiceRecord>('/voice-records', { upload_id: uploadId }),
  get: (id: string) => api.get<VoiceRecord>(`/voice-records/${id}`),
  retry: (id: string) => api.post<VoiceRecord>(`/voice-records/${id}/retry`),
  confirm: (id: string, candidate: VoiceCandidate) =>
    api.post<{ entity_type: string; entity_id: string }>(`/voice-records/${id}/confirm`, {
      schema_version: 'voice-task.v1',
      candidate,
    }),
}

// Binary upload helper (client.ts only handles JSON bodies).
export async function uploadAudioBytes(
  uploadId: string,
  blob: Blob,
  csrfToken: string | null,
): Promise<void> {
  const resp = await fetch(`/api/v1/uploads/${uploadId}/content`, {
    method: 'PUT',
    headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : {},
    body: blob,
    credentials: 'same-origin',
  })
  if (!resp.ok) throw new Error(`upload failed: ${resp.status}`)
}
