export type AgentResultTone = 'neutral' | 'success' | 'warning' | 'danger'

export interface AgentResultDetail {
  label: string
  value: string
}

export interface AgentResultItemView {
  key: string
  id: string | null
  title: string
  description: string | null
  link: string | null
  category: string | null
  tags: string[]
  status: string | null
  tone: AgentResultTone
  metrics: AgentResultDetail[]
  details: AgentResultDetail[]
  searchText: string
}

export interface AgentResultPresentation {
  items: AgentResultItemView[]
  summary: string | null
  total: number | null
}

type JsonRecord = Record<string, unknown>

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const COLLECTION_KEYS = ['items', 'results', 'posts', 'categories', 'tags'] as const
const HIDDEN_DETAIL_KEYS = new Set([
  'id', 'post_id', 'object_id', 'title', 'name', 'label', 'link', 'url',
  'summary', 'highlight', 'description', 'reason', 'error', 'error_reason',
  'category', 'category_id', 'tags', 'tag_ids', 'status', 'content_status',
  'verified', 'ok', 'usage_count', 'source_count', 'updated_at', 'created_at',
  'published_at', 'occurred_at', 'markdown', 'structured_data', 'source_refs',
  '_display_status', '_display_tone',
])

const FIELD_LABELS: Record<string, string> = {
  content_class: '内容类型',
  matched_fields: '匹配位置',
  ai_state: 'AI 状态',
  time: '时间',
  time_basis: '时间依据',
  version: '版本',
  expected: '预期值',
  observed: '实际值',
  intended_tags: '建议标签',
  observed_tags: '当前标签',
  fields: '变更字段',
  operation_type: '操作类型',
}

const STATUS_LABELS: Record<string, string> = {
  published: '已发布',
  private: '私密',
  draft: '草稿',
  active: '可用',
  success: '成功',
  partial_success: '部分成功',
  failed: '失败',
  skipped: '已跳过',
  conflict: '存在冲突',
  verified: '已验证',
  matched: '已匹配',
}

function isRecord(value: unknown): value is JsonRecord {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function text(value: unknown): string | null {
  if (typeof value === 'string') {
    const cleaned = value.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim()
    return cleaned || null
  }
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

function firstText(record: JsonRecord, keys: string[]): string | null {
  for (const key of keys) {
    const found = text(record[key])
    if (found) return found
  }
  return null
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => text(item)).filter((item): item is string => !!item)
}

function friendlyValue(value: unknown): string | null {
  const direct = text(value)
  if (direct) return direct
  if (Array.isArray(value)) {
    const values = value.map((item) => friendlyValue(item)).filter((item): item is string => !!item)
    return values.length ? values.slice(0, 12).join('、') : null
  }
  if (isRecord(value)) {
    const values = Object.entries(value)
      .map(([key, item]) => {
        const rendered = friendlyValue(item)
        return rendered ? `${FIELD_LABELS[key] ?? key}：${rendered}` : null
      })
      .filter((item): item is string => !!item)
    return values.length ? values.slice(0, 6).join('；') : null
  }
  return null
}

function toneFor(record: JsonRecord, status: string | null): AgentResultTone {
  const explicit = text(record._display_tone)
  if (explicit && ['neutral', 'success', 'warning', 'danger'].includes(explicit)) {
    return explicit as AgentResultTone
  }
  if (record.verified === true || record.ok === true || status === 'verified' || status === 'success') {
    return 'success'
  }
  if (record.verified === false || status === 'conflict' || status === 'partial_success') {
    return 'warning'
  }
  if (record.ok === false || status === 'failed') return 'danger'
  return 'neutral'
}

function itemView(record: JsonRecord, index: number): AgentResultItemView {
  const id = firstText(record, ['id', 'post_id', 'object_id'])
  const fallbackTitle = id ? `文章 ${id.slice(0, 8)}` : `结果 ${index + 1}`
  const title = firstText(record, ['title', 'name', 'label']) ?? fallbackTitle
  const description = firstText(record, [
    'highlight', 'summary', 'description', 'reason', 'error_reason', 'error', 'result_summary',
  ])
  const rawStatus = firstText(record, ['_display_status', 'status', 'content_status'])
  const status = rawStatus ? (STATUS_LABELS[rawStatus] ?? rawStatus) : null
  const explicitLink = firstText(record, ['link', 'url'])
  const link = explicitLink?.startsWith('/')
    ? explicitLink
    : id && UUID_PATTERN.test(id) && (record.title || record.post_id || record.tags)
      ? `/blog/${id}/view`
      : null
  const tags = stringList(record.tags).length
    ? stringList(record.tags)
    : stringList(record.observed_tags).length
      ? stringList(record.observed_tags)
      : stringList(record.intended_tags)
  const metrics: AgentResultDetail[] = []
  if (typeof record.usage_count === 'number') {
    metrics.push({ label: '使用次数', value: String(record.usage_count) })
  }
  if (typeof record.source_count === 'number') {
    metrics.push({ label: '来源数量', value: String(record.source_count) })
  }
  const details = Object.entries(record)
    .filter(([key]) => !HIDDEN_DETAIL_KEYS.has(key))
    .map(([key, value]) => ({
      label: FIELD_LABELS[key] ?? key.replaceAll('_', ' '),
      value: friendlyValue(value),
    }))
    .filter((item): item is AgentResultDetail => !!item.value)
    .slice(0, 12)
  const category = firstText(record, ['category'])
  const searchText = [title, description, category, status, ...tags]
    .filter((value): value is string => !!value)
    .join(' ')
    .toLocaleLowerCase()
  return {
    key: id ?? `${title}-${index}`,
    id,
    title,
    description,
    link,
    category,
    tags,
    status,
    tone: toneFor(record, rawStatus),
    metrics,
    details,
    searchText,
  }
}

function locateRecords(value: unknown): { records: JsonRecord[]; wrapper: JsonRecord | null } {
  if (Array.isArray(value)) {
    return { records: value.filter(isRecord), wrapper: null }
  }
  if (!isRecord(value)) return { records: [], wrapper: null }
  if (isRecord(value.structured_content)) {
    const nested = locateRecords(value.structured_content)
    if (nested.records.length) return { records: nested.records, wrapper: nested.wrapper ?? value }
  }
  for (const key of COLLECTION_KEYS) {
    if (Array.isArray(value[key]) && value[key].some(isRecord)) {
      return { records: (value[key] as unknown[]).filter(isRecord), wrapper: value }
    }
  }
  if (value.id || value.post_id || value.object_id || value.title || value.name) {
    return { records: [value], wrapper: null }
  }
  return { records: [], wrapper: value }
}

export function presentAgentResult(value: unknown): AgentResultPresentation {
  if (typeof value === 'string') {
    return { items: [], summary: value.trim() || null, total: null }
  }
  const { records, wrapper } = locateRecords(value)
  const totalValue = wrapper?.total
  const total = typeof totalValue === 'number' ? totalValue : records.length || null
  const query = firstText(wrapper ?? {}, ['query', 'search'])
  const summary = query
    ? `“${query}”共找到 ${total ?? records.length} 项`
    : records.length
      ? `共 ${total ?? records.length} 项结果`
      : friendlyValue(wrapper)
  return { items: records.map(itemView), summary, total }
}

export function presentReportResults(report: {
  results: JsonRecord[]
  verified_changes: JsonRecord[]
  conflicts: JsonRecord[]
  failures: JsonRecord[]
  skipped: JsonRecord[]
  unprocessed: JsonRecord[]
}): AgentResultPresentation {
  const decorated = [
    ...report.results.map((item) => ({ ...item, _display_status: 'matched' })),
    ...report.verified_changes.map((item) => ({
      ...item, _display_status: 'verified', _display_tone: 'success',
    })),
    ...report.conflicts.map((item) => ({
      ...item, _display_status: 'conflict', _display_tone: 'warning',
    })),
    ...report.failures.map((item) => ({
      ...item, _display_status: 'failed', _display_tone: 'danger',
    })),
    ...report.skipped.map((item) => ({ ...item, _display_status: 'skipped' })),
    ...report.unprocessed.map((item) => ({
      ...item, _display_status: '未处理', _display_tone: 'warning',
    })),
  ]
  const merged = new Map<string, JsonRecord>()
  decorated.forEach((item, index) => {
    const key = firstText(item, ['id', 'post_id', 'object_id']) ?? `item-${index}`
    merged.set(key, { ...(merged.get(key) ?? {}), ...item })
  })
  const records = [...merged.values()]
  return {
    items: records.map(itemView),
    summary: records.length ? `共 ${records.length} 项可查看结果` : null,
    total: records.length || null,
  }
}

export function parseResultText(value: string): unknown | null {
  const trimmed = value.trim()
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return null
  try {
    return JSON.parse(trimmed) as unknown
  } catch {
    return null
  }
}
