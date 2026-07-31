<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ECharts, EChartsOption } from 'echarts'

const props = defineProps<{
  kind: 'mermaid' | 'echarts'
  source: string
  caption?: string
}>()

const canvas = ref<HTMLElement | null>(null)
const error = ref('')
let chart: ECharts | null = null
let renderSerial = 0

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
    return {
      tooltip: { trigger: 'item' },
      legend: { type: 'scroll', bottom: 0 },
      series: [{ name, type: 'pie', radius: ['35%', '68%'], data: points.map((p) => ({ name: p.label, value: p.value })) }],
    }
  }
  if (!['bar', 'line', 'scatter'].includes(value.chart_type || '')) return null
  const seriesType: 'bar' | 'line' | 'scatter' = value.chart_type as 'bar' | 'line' | 'scatter'
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 24, top: 24, bottom: 48, containLabel: true },
    xAxis: { type: 'category', data: labels },
    yAxis: { type: 'value', name },
    series: [{ name, type: seriesType, data: values, smooth: seriesType === 'line' }],
  }
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
    error.value = props.kind === 'mermaid' ? '流程图暂时无法渲染' : '图表数据暂时无法渲染'
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
    <figcaption>{{ caption || (kind === 'mermaid' ? '流程图' : '数据图表') }}</figcaption>
    <div
      ref="canvas"
      class="visual-canvas"
      role="img"
      :aria-label="caption || (kind === 'mermaid' ? '流程图' : '数据图表')"
    />
    <p
      v-if="error"
      class="visual-error"
    >
      {{ error }}，可展开查看源数据。
    </p>
    <details class="visual-source">
      <summary>查看源代码</summary>
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
  min-height: 180px;
  width: 100%;
  overflow-x: auto;
}
.visual-canvas :deep(svg) {
  max-width: 100%;
  height: auto;
}
.visual-error {
  color: var(--color-danger, #b91c1c);
  font-size: 0.85rem;
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
