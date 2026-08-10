import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, setCsrfToken } from '@/api/client'

describe('api client CSRF recovery', () => {
  beforeEach(() => {
    setCsrfToken('stale-token')
  })

  afterEach(() => {
    setCsrfToken(null)
    vi.restoreAllMocks()
  })

  it('refreshes the session and retries once after csrf_failed', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        type: 'about:blank',
        title: 'Forbidden',
        status: 403,
        code: 'csrf_failed',
      }), {
        status: 403,
        headers: { 'content-type': 'application/problem+json' },
      }))
      .mockResolvedValueOnce(new Response(null, {
        status: 204,
        headers: { 'X-CSRF-Token': 'fresh-token' },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'job-1' }), {
        status: 202,
        headers: { 'content-type': 'application/json' },
      }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.post('/posts/post-1/optimize', {
      post_version: 1,
      optimization_type: 'full',
    })).resolves.toEqual({ id: 'job-1' })

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/posts/post-1/optimize')
    expect(fetchMock.mock.calls[0][1].headers['X-CSRF-Token']).toBe('stale-token')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/auth/refresh')
    expect(fetchMock.mock.calls[2][1].headers['X-CSRF-Token']).toBe('fresh-token')
  })
})
