// Typed fetch wrapper: same-origin cookies, CSRF header on unsafe methods,
// automatic one-shot refresh on 401, and RFC 9457 Problem Details mapping.

export interface ProblemDetails {
  type: string
  title: string
  status: number
  detail?: string
  code?: string
  trace_id?: string
  errors?: Array<Record<string, unknown>>
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly problem: ProblemDetails
  constructor(problem: ProblemDetails) {
    super(problem.detail ?? problem.title)
    this.status = problem.status
    this.code = problem.code ?? 'error'
    this.problem = problem
  }
}

const UNSAFE = new Set(['POST', 'PATCH', 'PUT', 'DELETE'])

// The CSRF token is returned by login/refresh and kept in memory only.
let csrfToken: string | null = null

export function setCsrfToken(token: string | null): void {
  csrfToken = token
}

export function getCsrfToken(): string | null {
  return csrfToken
}

interface RequestOptions {
  method?: string
  body?: unknown
  query?: Record<string, string | number | boolean | undefined | null>
  signal?: AbortSignal
  _retried?: boolean
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = `/api/v1${path}`
  if (!query) return url
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null) params.append(k, String(v))
  }
  const qs = params.toString()
  return qs ? `${url}?${qs}` : url
}

async function toProblem(resp: Response): Promise<ProblemDetails> {
  try {
    const data = (await resp.json()) as ProblemDetails
    if (data && typeof data.status === 'number') return data
  } catch {
    // fall through
  }
  return { type: 'about:blank', title: resp.statusText, status: resp.status }
}

// Refresh is attempted at most once per failed request; concurrent 401s share it.
let refreshInFlight: Promise<boolean> | null = null

async function tryRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const resp = await fetch(buildUrl('/auth/refresh'), {
        method: 'POST',
        headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : {},
        credentials: 'same-origin',
      })
      if (resp.ok) {
        const newToken = resp.headers.get('X-CSRF-Token')
        if (newToken) setCsrfToken(newToken)
        return true
      }
      return false
    })().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers: Record<string, string> = {}
  let body: BodyInit | undefined
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }
  if (UNSAFE.has(method) && csrfToken) {
    headers['X-CSRF-Token'] = csrfToken
  }

  const resp = await fetch(buildUrl(path, options.query), {
    method,
    headers,
    body,
    credentials: 'same-origin',
    signal: options.signal,
  })

  if (resp.status === 401 && !options._retried && path !== '/auth/login') {
    const refreshed = await tryRefresh()
    if (refreshed) {
      return apiRequest<T>(path, { ...options, _retried: true })
    }
  }

  if (!resp.ok) {
    throw new ApiError(await toProblem(resp))
  }

  if (resp.status === 204) return undefined as T
  const contentType = resp.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    return (await resp.json()) as T
  }
  return (await resp.text()) as unknown as T
}

export const api = {
  get: <T>(path: string, query?: RequestOptions['query']) => apiRequest<T>(path, { query }),
  post: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: 'POST', body }),
  patch: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: 'PATCH', body }),
  del: <T>(path: string) => apiRequest<T>(path, { method: 'DELETE' }),
}
