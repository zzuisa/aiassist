import { api } from '@/api/client'
import { getCsrfToken } from '@/api/client'

export interface ProvenancedValue {
  value: string
  source: 'user' | 'ai' | 'extracted'
  confidence?: number | null
}

export interface CaptureAsset {
  id: string
  role: 'original' | 'thumbnail' | 'preview' | 'attachment' | 'audio'
  media_type?: string | null
  byte_size?: number | null
  width?: number | null
  height?: number | null
  status: string
}

export interface Capture {
  id: string
  type: string
  private: boolean
  fields: Record<string, ProvenancedValue>
  assets: CaptureAsset[]
  processing_status: 'pending' | 'processing' | 'ready' | 'needs_input' | 'failed'
  possible_duplicate_of?: string | null
  usage_status: string
  ocr_text?: string | null
  version: number
  created_at: string
}

export interface CapturePage {
  items: Capture[]
  next_cursor?: string | null
}

export const capturesApi = {
  list: (query?: Record<string, string>) => api.get<CapturePage>('/captures', query),
  get: (id: string) => api.get<Capture>(`/captures/${id}`),
  create: (type: string, title: string | null, uploadIds: string[]) =>
    api.post<Capture>('/captures', { type, title, upload_ids: uploadIds }),
  patch: (id: string, body: Record<string, unknown>) => api.patch<Capture>(`/captures/${id}`, body),
  remove: (id: string) => api.del<void>(`/captures/${id}`),
  convert: (id: string, targetType: string) =>
    api.post<{ type: string; id: string }>(`/captures/${id}/convert`, { target_type: targetType }),
  assetAccess: (captureId: string, assetId: string) =>
    api.get<{ url: string; expires_at: string }>(
      `/captures/${captureId}/assets/${assetId}/access`,
    ),
}

// Upload an image and create a capture in one save-first flow.
export async function uploadImageAndCreateCapture(
  file: File,
  title: string | null,
): Promise<Capture> {
  const session = await api.post<{ id: string }>('/uploads', {
    purpose: 'capture',
    filename: file.name,
    media_type: file.type,
    byte_size: file.size,
  })
  const put = await fetch(`/api/v1/uploads/${session.id}/content`, {
    method: 'PUT',
    headers: getCsrfToken() ? { 'X-CSRF-Token': getCsrfToken()! } : {},
    body: file,
    credentials: 'same-origin',
  })
  if (!put.ok) throw new Error(`upload failed: ${put.status}`)
  await api.post(`/uploads/${session.id}/complete`)
  return capturesApi.create('item', title, [session.id])
}
