export interface ReleaseEntry {
  id: string
  version: string
  commit: string
  commit_short: string
  message: string
  changes: string[]
  changed_files: string[]
  deployed_at: string
  environment: string
  git_pushed: boolean
  deployment_status: 'verified' | 'deploying' | 'failed'
  migration_head: string | null
}

export interface ReleaseHistory {
  releases: ReleaseEntry[]
}

async function fetchReleaseHistory(): Promise<ReleaseHistory> {
  const response = await fetch(`/release-history.json?ts=${Date.now()}`, {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`release history request failed: ${response.status}`)
  const data = await response.json() as ReleaseHistory
  if (!data || !Array.isArray(data.releases)) throw new Error('invalid release history')
  return data
}

export const releasesApi = {
  history: fetchReleaseHistory,
}
