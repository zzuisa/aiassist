<script setup lang="ts">
/* eslint-disable no-undef -- browser globals are provided by the PWA runtime. */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ECharts, EChartsOption } from 'echarts'

type VisualKind = 'mermaid' | 'visual-plan' | 'echarts'
type VisualNode = { id: string; label: string; detail?: string; icon?: string }
type VisualEdge = { from: string; to: string; label?: string }
type VisualPlan = {
  visual_type: string
  layout: string
  theme: string
  title: string
  nodes: VisualNode[]
  edges: VisualEdge[]
}

const props = defineProps<{
  kind: VisualKind
  source: string
  caption?: string
}>()

const canvas = ref<HTMLElement | null>(null)
const error = ref('')
let chart: ECharts | null = null
let renderSerial = 0

const themeMap: Record<string, { background: string; ink: string; muted: string; colors: string[] }> = {
  warm: { background: '#fff8f1', ink: '#3b2f2a', muted: '#806d62', colors: ['#f6bd60', '#f28482', '#84a59d', '#f5cac3'] },
  fresh: { background: '#f2fbf8', ink: '#173b3a', muted: '#567674', colors: ['#69c6b0', '#8dc6ff', '#f5c46b', '#d6a2e8'] },
  calm: { background: '#f5f7ff', ink: '#2f3658', muted: '#68708e', colors: ['#91a7ff', '#a5d8ff', '#b2f2bb', '#ffd8a8'] },
  energetic: { background: '#fff8f0', ink: '#402a20', muted: '#856657', colors: ['#ff922b', '#ff6b6b', '#845ef7', '#20c997'] },
  neutral: { background: '#f7f8fa', ink: '#27303b', muted: '#66717e', colors: ['#94a3b8', '#60a5fa', '#34d399', '#fbbf24'] },
}

const iconMap: Record<string, string> = {
  book: '▤', check: '✓', heart: '♥', light: '☼', moon: '☾', spark: '✦', star: '★', step: '•', sun: '☀', target: '◎',
}

function xml(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function lines(value: string, max = 16): string[] {
  const chars = Array.from(value)
  const chunks: string[] = []
  for (let i = 0; i < chars.length; i += max) chunks.push(chars.slice(i, i + max).join(''))
  return chunks.slice(0, 3)
}

function parseVisualPlan(source: string): VisualPlan | null {
  try {
    const parsed: unknown = JSON.parse(source)
    const value = (
      parsed && typeof parsed === 'object' && 'visual_plan' in parsed
        ? (parsed as { visual_plan?: unknown }).visual_plan
        : parsed
    ) as Partial<VisualPlan> | null
    if (!value || !Array.isArray(value.nodes) || value.nodes.length < 1) return null
    if (typeof value.title !== 'string' || !Array.isArray(value.edges)) return null
    const nodes = value.nodes as VisualNode[]
    const edges = value.edges as VisualEdge[]
    const ids = new Set(nodes.map((node) => node.id))
    if (ids.size !== nodes.length || nodes.some((node) => !node.id || !node.label)) return null
    if (edges.some((edge) => !ids.has(edge.from) || !ids.has(edge.to))) return null
    return value as VisualPlan
  } catch {
    return null
  }
}

function nodePositions(plan: VisualPlan, width: number, height: number): Map<string, { x: number; y: number }> {
  const nodeWidth = 190
  const nodeHeight = 86
  const positions = new Map<string, { x: number; y: number }>()
  const columns = plan.layout === 'compact_vertical' ? 1 : plan.nodes.length <= 4 ? plan.nodes.length : 3
  const rows = Math.ceil(plan.nodes.length / columns)
  const horizontalGap = columns === 1 ? 0 : Math.max(18, (width - 40 - columns * nodeWidth) / Math.max(1, columns - 1))
  const verticalGap = Math.max(20, (height - 96 - rows * nodeHeight) / Math.max(1, rows - 1))
  const contentWidth = columns * nodeWidth + Math.max(0, columns - 1) * horizontalGap
  const startX = (width - contentWidth) / 2
  for (let index = 0; index < plan.nodes.length; index += 1) {
    const row = Math.floor(index / columns)
    const column = index % columns
    positions.set(plan.nodes[index].id, {
      x: startX + column * (nodeWidth + horizontalGap),
      y: 74 + row * (nodeHeight + verticalGap),
    })
  }
  return positions
}

function visualPlanSvg(plan: VisualPlan): string {
  const theme = themeMap[plan.theme] ?? themeMap.neutral
  const nodeWidth = 190
  const nodeHeight = 86
  const columns = plan.layout === 'compact_vertical' ? 1 : plan.nodes.length <= 4 ? plan.nodes.length : 3
  const rows = Math.ceil(plan.nodes.length / columns)
  const width = Math.min(900, Math.max(360, columns * nodeWidth + (columns - 1) * 26 + 40))
  const height = 74 + rows * nodeHeight + Math.max(0, rows - 1) * 24 + 28
  const positions = nodePositions(plan, width, height)
  const markerId = `arrow-${plan.theme.replace(/[^A-Za-z0-9_-]/g, '-')}`
  const edgeSvg = plan.edges.map((edge) => {
    const from = positions.get(edge.from)
    const to = positions.get(edge.to)
    if (!from || !to) return ''
    let x1 = from.x + nodeWidth / 2
    let y1 = from.y + nodeHeight / 2
    let x2 = to.x + nodeWidth / 2
    let y2 = to.y + nodeHeight / 2
    const horizontal = Math.abs(x2 - x1) >= Math.abs(y2 - y1)
    if (horizontal) {
      const direction = x2 >= x1 ? 1 : -1
      x1 += direction * nodeWidth / 2
      x2 -= direction * nodeWidth / 2
    } else {
      const direction = y2 >= y1 ? 1 : -1
      y1 += direction * nodeHeight / 2
      y2 -= direction * nodeHeight / 2
    }
    const curve = Math.abs(y2 - y1) > 12 ? 22 : 12
    const controlY = (y1 + y2) / 2 + (y2 >= y1 ? -curve : curve)
    const label = edge.label ? `<text x="${(x1 + x2) / 2}" y="${controlY - 5}" text-anchor="middle" class="edge-label">${xml(edge.label)}</text>` : ''
    return `<path d="M ${x1} ${y1} Q ${(x1 + x2) / 2} ${controlY} ${x2} ${y2}" class="edge" marker-end="url(#${markerId})" />${label}`
  }).join('')
  const nodesSvg = plan.nodes.map((node, index) => {
    const position = positions.get(node.id)
    if (!position) return ''
    const accent = theme.colors[index % theme.colors.length]
    const labelLines = lines(node.label, 14)
    const detailLines = lines(node.detail || '', 22)
    const icon = iconMap[node.icon || 'step'] || '•'
    const labelSvg = labelLines.map((line, i) => `<tspan x="${position.x + 48}" dy="${i === 0 ? 0 : 18}">${xml(line)}</tspan>`).join('')
    const detailSvg = detailLines.map((line, i) => `<tspan x="${position.x + 48}" dy="${i === 0 ? 0 : 14}">${xml(line)}</tspan>`).join('')
    return `<g class="node"><rect x="${position.x}" y="${position.y}" width="${nodeWidth}" height="${nodeHeight}" rx="18" fill="#fff" stroke="${accent}" stroke-width="2"/><circle cx="${position.x + 28}" cy="${position.y + 29}" r="17" fill="${accent}"/><text x="${position.x + 28}" y="${position.y + 35}" text-anchor="middle" class="icon">${xml(icon)}</text><text x="${position.x + 48}" y="${position.y + 30}" class="node-label">${labelSvg}</text><text x="${position.x + 48}" y="${position.y + 62}" class="node-detail">${detailSvg}</text></g>`
  }).join('')
  const titleLines = lines(plan.title, 30)
  const titleSvg = titleLines.map((line, i) => `<tspan x="${width / 2}" dy="${i === 0 ? 0 : 22}">${xml(line)}</tspan>`).join('')
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${xml(plan.title)}"><defs><marker id="${markerId}" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M 0 0 L 8 4 L 0 8 z" fill="${theme.muted}"/></marker></defs><rect width="${width}" height="${height}" rx="24" fill="${theme.background}"/><text x="${width / 2}" y="30" text-anchor="middle" class="title">${titleSvg}</text><g class="edges">${edgeSvg}</g><g class="nodes">${nodesSvg}</g><style>.title{font:700 17px system-ui,-apple-system,"Segoe UI",sans-serif;fill:${theme.ink}}.edge{fill:none;stroke:${theme.muted};stroke-width:2;stroke-linecap:round;opacity:.8}.edge-label{font:500 11px system-ui,-apple-system,"Segoe UI",sans-serif;fill:${theme.muted};paint-order:stroke;stroke:${theme.background};stroke-width:5px;stroke-linejoin:round}.icon{font:700 18px system-ui,-apple-system,"Segoe UI Symbol",sans-serif;fill:#fff}.node-label{font:700 14px system-ui,-apple-system,"Segoe UI",sans-serif;fill:${theme.ink}}.node-detail{font:500 11px system-ui,-apple-system,"Segoe UI",sans-serif;fill:${theme.muted}}</style></svg>`
}

function chartOption(input: unknown): EChartsOption | null {
  if (!input || typeof input !== 'object') return null
  const value = input as { chart_type?: string; data?: unknown[]; unit?: string }
  if (!Array.isArray(value.data) || value.data.length < 2 || value.data.length > 100) return null
  const points = value.data.filter((item): item is { label: string; value: number } => {
    if (!item || typeof item !== 'object') return false
    const point = item as { label?: unknown; value?: unknown }
    return typeof point.label === 'string' && typeof point.value === 'number' && Number.isFinite(point.value)
  })
  if (points.length !== value.data.length) return null
  const labels = points.map((point) => point.label)
  const values = points.map((point) => point.value)
  const name = value.unit || '数值'
  if (value.chart_type === 'pie') {
    return { tooltip: { trigger: 'item' }, legend: { type: 'scroll', bottom: 0 }, series: [{ name, type: 'pie', radius: ['35%', '68%'], data: points.map((p) => ({ name: p.label, value: p.value })) }] }
  }
  if (!['bar', 'line', 'scatter'].includes(value.chart_type || '')) return null
  const seriesType: 'bar' | 'line' | 'scatter' = value.chart_type as 'bar' | 'line' | 'scatter'
  return { tooltip: { trigger: 'axis' }, grid: { left: 48, right: 24, top: 24, bottom: 48, containLabel: true }, xAxis: { type: 'category', data: labels }, yAxis: { type: 'value', name }, series: [{ name, type: seriesType, data: values, smooth: seriesType === 'line' }] }
}

async function render(): Promise<void> {
  const target = canvas.value
  if (!target) return
  const serial = ++renderSerial
  error.value = ''
  if (chart) {
    chart.dispose()
    chart = null
  }
  target.innerHTML = ''
  try {
    if (props.kind === 'visual-plan') {
      const plan = parseVisualPlan(props.source)
      if (!plan) throw new Error('invalid visual plan')
      target.innerHTML = visualPlanSvg(plan)
      return
    }
    if (props.kind === 'mermaid') {
      const { default: mermaid } = await import('mermaid')
      mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'default' })
      const rendered = await mermaid.render(`blog-visual-${serial}`, props.source)
      if (serial !== renderSerial || !canvas.value) return
      canvas.value.innerHTML = rendered.svg
      rendered.bindFunctions?.(canvas.value)
      return
    }
    const option = chartOption(JSON.parse(props.source))
    if (!option) throw new Error('invalid chart')
    const echarts = await import('echarts')
    chart = echarts.init(target, undefined, { renderer: 'canvas' })
    chart.setOption(option)
  } catch {
    error.value = props.kind === 'visual-plan' ? '文章要点图暂时无法渲染' : props.kind === 'mermaid' ? '流程图暂时无法渲染' : '数据图表暂时无法渲染'
  }
}

function resize(): void {
  chart?.resize()
}

onMounted(async () => {
  await nextTick()
  await render()
  window.addEventListener('resize', resize)
})
watch(() => [props.kind, props.source], () => void render())
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
})
</script>

<template>
  <figure class="visual-block md-special">
    <figcaption>{{ caption || (kind === 'visual-plan' ? '文章要点图' : kind === 'mermaid' ? '流程图' : '数据图表') }}</figcaption>
    <div
      ref="canvas"
      class="visual-canvas"
      role="img"
      :aria-label="caption || (kind === 'visual-plan' ? '文章要点图' : kind === 'mermaid' ? '流程图' : '数据图表')"
    />
    <p
      v-if="error"
      class="visual-error"
    >
      {{ error }}，可展开查看视觉方案数据。
    </p>
    <details class="visual-source">
      <summary>{{ kind === 'visual-plan' ? '查看视觉方案数据' : '查看源代码' }}</summary>
      <pre>{{ source }}</pre>
    </details>
  </figure>
</template>

<style scoped>
.visual-block {
  margin: var(--space-3) 0;
  padding: var(--space-3);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 10px);
  background: var(--color-surface, #fff);
}
.visual-block figcaption {
  margin-bottom: var(--space-2);
  color: var(--color-text-muted);
  font-size: 0.85rem;
  font-weight: 600;
}
.visual-canvas {
  min-height: 120px;
  width: 100%;
  overflow-x: auto;
}
.visual-canvas :deep(svg) {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
}
.visual-error {
  color: var(--color-danger, #b91c1c);
  font-size: 0.8rem;
}
.visual-source {
  margin-top: var(--space-2);
  color: var(--color-text-muted);
  font-size: 0.8rem;
}
.visual-source pre {
  max-height: 220px;
  overflow: auto;
  white-space: pre-wrap;
}
</style>
